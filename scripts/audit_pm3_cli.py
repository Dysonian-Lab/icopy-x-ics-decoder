#!/usr/bin/env python3
"""audit_pm3_cli.py -- PM3 command & parser inventory for AutoCopy.

Inspects release/extracted-955/lib/ for PM3 command dispatch points.
For each dispatch point, extracts:
    - File and line number
    - Target card/tag context (e.g., HID, Mifare Classic Gen1a, Indala, T55xx, etc.)
    - Command pattern/template dispatched to PM3
    - Whether it routes through pm3_compat.py or directly to executor
    - Corresponding response parser or regex used for success evaluation

Output is grouped by card category:
    1. LF Clone Writes & Verifications (T5577 targets)
    2. HF Mifare Classic (Gen1a vs Standard/Gen2)
    3. HF Ultralight / NTAG
    4. LF Hitag2 / Paxton
    5. HF iCLASS & ISO15693

Usage:
    python scripts/audit_pm3_cli.py
"""

import ast
import os
import re
import sys

TARGET_DIR = os.path.join("release", "extracted-955", "lib")
TARGET_FILES = [
    "scan.py",
    "write.py",
    "lfwrite.py",
    "hfmfwrite.py",
    "hfmfuwrite.py",
    "iclasswrite.py",
    "lfverify.py",
]

PM3_CALL_ATTRS = {"startPM3Task", "sendCommand", "exec_cmd", "pm3_cmd"}


def build_function_scoped_var_maps(tree):
    """Build per-function and module-level variable maps with line-aware scoping.

    Also tracks for-loop variables and their iterable sources.

    Returns:
        module_vars: dict of var_name -> list of (line_no, AST node) tuples
        func_vars: dict of func_name -> dict of var_name -> list of (line_no, AST node)
        loop_vars: dict of func_name -> dict of loop_var_name -> (line_start, line_end, iter_node)
    """
    module_vars = {}
    func_vars = {}
    loop_vars = {}

    # Module-level assignments (only direct children of Module body)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id not in module_vars:
                        module_vars[target.id] = []
                    module_vars[target.id].append((node.lineno, node.value))

    # Per-function assignments and loop variables
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_name = node.name
            if func_name not in func_vars:
                func_vars[func_name] = {}
            if func_name not in loop_vars:
                loop_vars[func_name] = {}
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            if target.id not in func_vars[func_name]:
                                func_vars[func_name][target.id] = []
                            func_vars[func_name][target.id].append(
                                (child.lineno, child.value)
                            )
                elif isinstance(child, ast.For):
                    if isinstance(child.target, ast.Name):
                        loop_vars[func_name][child.target.id] = (
                            child.lineno, child.body[0].lineno if child.body else child.lineno,
                            child.iter
                        )

    return module_vars, func_vars, loop_vars


def resolve_var_at_line(var_assignments, line_no):
    """Given a list of (line, value) tuples, find the assignment active at line_no.

    Returns the AST value node for the assignment with the highest line number
    that is <= line_no (i.e., the most recent assignment before this line).
    """
    if not var_assignments:
        return None
    best = None
    best_line = -1
    for vline, vvalue in var_assignments:
        if vline <= line_no and vline > best_line:
            best = vvalue
            best_line = vline
    if best is None:
        # Variable assigned after this point; use first assignment as estimate
        best = var_assignments[0][1]
    return best


def build_line_scoped_var_map(func_var_lists, module_var_lists, line_no):
    """Build a var -> AST node map for a specific line number within a function.

    Uses the most recent assignment before `line_no` for each variable.
    Falls back to module-level assignments for module-level variables.
    """
    result = {}
    for var_name, assignments in func_var_lists.items():
        value_node = resolve_var_at_line(assignments, line_no)
        if value_node is not None:
            result[var_name] = value_node
    for var_name, assignments in module_var_lists.items():
        if var_name not in result:
            value_node = resolve_var_at_line(assignments, line_no)
            if value_node is not None:
                result[var_name] = value_node
    return result


def find_enclosing_function(tree, target_node):
    """Find the name of the function definition that contains target_node."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target_node:
                    return node.name
    return None


def infer_placeholder_from_arg(arg):
    """Infer a meaningful placeholder name from a function call argument."""
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    if isinstance(arg, ast.Subscript):
        val = infer_placeholder_from_arg(arg.value)
        return f"item_{val}"
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Constant):
        return str(arg.value)
    return "expr"


def resolve_command_builder_call(node, tree, var_map, depth=0):
    """If node is a call to a function that returns a command string,
    resolve it by inlining the function's return value."""
    if depth > 5:
        return None
    if not isinstance(node, ast.Call):
        return None

    func_name = None
    if isinstance(node.func, ast.Name):
        func_name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        func_name = node.func.attr

    if func_name is None:
        return None

    # Find the function definition in the tree
    for item in ast.walk(tree):
        if isinstance(item, ast.FunctionDef) and item.name == func_name:
            # Build a local var_map for the function call context
            # Map positional args to parameter names
            param_names = []
            for arg in item.args.args:
                param_names.append(arg.arg)

            # Create argument bindings: param_name -> arg expression
            arg_map = {}
            for i, arg in enumerate(node.args):
                if i < len(param_names):
                    arg_map[param_names[i]] = arg
            for kw in node.keywords:
                if kw.arg:
                    arg_map[kw.arg] = kw.value

            # Merge with existing var_map
            local_map = dict(var_map) if var_map else {}
            local_map.update(arg_map)

            # Walk the function body to find a return with a string
            for fn_node in ast.walk(item):
                if isinstance(fn_node, ast.Return) and fn_node.value is not None:
                    return extract_command_template(fn_node.value, local_map, tree, depth + 1)
            return None

    return None


def extract_command_template(node, var_map=None, tree=None, depth=0):
    if node is None:
        return ""
    if depth > 15:
        return "<deep>"

    if isinstance(node, ast.Name):
        if var_map is not None and node.id in var_map:
            resolved = extract_command_template(var_map[node.id], var_map, tree, depth + 1)
            # If the resolved value is a list of strings (from a for-loop iterable),
            # try to extract the individual items
            if isinstance(var_map[node.id], ast.List):
                items = []
                for elt in var_map[node.id].elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        items.append(elt.value)
                    elif isinstance(elt, ast.JoinedStr):
                        parts = []
                        for v in elt.values:
                            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                parts.append(v.value)
                            elif isinstance(v, ast.FormattedValue):
                                ph = infer_placeholder_from_arg(v.value)
                                parts.append("{" + ph + "}")
                        items.append("".join(parts))
                if items:
                    return "  OR  ".join(items)
            if resolved and resolved != "<" + node.id + ">":
                return resolved
        return "<" + node.id + ">"

    # If node is a Call to a known command-builder function, try to inline it
    if isinstance(node, ast.Call) and tree is not None:
        inlined = resolve_command_builder_call(node, tree, var_map, depth)
        if inlined:
            return inlined

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value

    if isinstance(node, ast.Constant):
        return str(node.value)

    if isinstance(node, ast.JoinedStr):
        parts = []
        for val_node in node.values:
            if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
                parts.append(val_node.value)
            elif isinstance(val_node, ast.FormattedValue):
                ph = infer_placeholder_from_arg(val_node.value)
                parts.append("{" + ph + "}")
            else:
                parts.append("{expr}")
        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = extract_command_template(node.left, var_map, tree, depth + 1)
        right = extract_command_template(node.right, var_map, tree, depth + 1)
        return left + right

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = extract_command_template(node.left, var_map, tree, depth + 1)
        right = extract_command_template(node.right, var_map, tree, depth + 1)
        return left.replace("%s", "{" + right + "}") if right else left

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        # Handle RAW_CLONE_MAP[typ].format(raw) which is an ast.Call with
        # the .format() being an attribute on a Subscript result
        # This is already handled in the Attribute case below
        if node.func.id in ("str", "hex", "bytes"):
            return "{" + node.func.id + "}"
        if node.func.id == "format":
            return "{format_result}"
        # For other direct function calls that return strings, try to
        # infer from context
        return "<" + node.func.id + "_result>"

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            template = extract_command_template(node.func.value, var_map, tree, depth + 1)
            args = []
            for arg in node.args:
                ph = infer_placeholder_from_arg(arg)
                args.append("{" + ph + "}")
            result = template
            for a in args:
                result = result.replace("{}", a, 1)
            return result
        if node.func.attr == "format_map":
            template = extract_command_template(node.func.value, var_map, tree, depth + 1)
            return template
        return "<" + node.func.attr + "_result>"

    if isinstance(node, ast.Attribute):
        return "<attr:" + node.attr + ">"

    if isinstance(node, ast.Subscript):
        # Handle RAW_CLONE_MAP[typ] patterns
        value = extract_command_template(node.value, var_map, tree, depth + 1)
        slice_str = extract_command_template(node.slice, var_map, tree, depth + 1)
        # If the value is already a resolved template (from a dict), return it directly
        if not value.startswith("<"):
            return value
        return "<dict_lookup:" + value + "[" + slice_str + "]>"

    if isinstance(node, ast.Dict):
        # Extract template patterns from dict values (e.g. RAW_CLONE_MAP)
        templates = []
        for v in node.values:
            tpl = extract_command_template(v, var_map, tree, depth + 1)
            if tpl and not tpl.startswith("<"):
                templates.append(tpl)
        if templates:
            if len(templates) == 1:
                return templates[0]
            return "  OR  ".join(templates)
        return "<dict_values>"

    return "<expr>"


def is_pm3_dispatch_call(node):
    """Return (func_name, command_arg_node, is_compat) if node is a PM3 dispatch call."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func

    if isinstance(func, ast.Attribute) and "translate" in func.attr:
        if node.args:
            return (func.attr, node.args[0], True)

    if isinstance(func, ast.Attribute) and func.attr in PM3_CALL_ATTRS:
        if node.args:
            return (func.attr, node.args[0], False)

    if isinstance(func, ast.Name) and func.id in PM3_CALL_ATTRS:
        if node.args:
            return (func.id, node.args[0], False)

    return None


def classify_card_context(filepath, function_name, cmd):
    """Determine the target card context for a command."""
    fname = os.path.basename(filepath)
    cmd_lower = cmd.lower().strip()
    fn_lower = function_name.lower()

    context_map = {
        "lfwrite.py": {
            "em 410x": "EM410x clone (T5577)",
            "hid": "HID Prox clone (T5577)",
            "indala": "Indala clone (T5577)",
            "fdxb": "FDX-B clone (T5577)",
            "keri": "KERI clone (T5577)",
            "nedap": "NEDAP clone (T5577)",
            "securakey": "SecuraKey clone (T5577)",
            "gallagher": "Gallagher clone (T5577)",
            "paradox": "Paradox clone (T5577)",
            "nexwatch": "Nexwatch clone (T5577)",
            "pac": "PAC/Stanley clone (T5577)",
            "t55xx restore": "T55xx dump restore",
            "t55xx write": "T55xx block write",
            "em 4x05 write": "EM4x05 block write",
            "em 4x05 read": "EM4x05 block read (verify)",
            "hitag wrbl": "Hitag2/Paxton block write",
            "hitag read": "Hitag2 authenticated read",
        },
    }

    if fname in context_map:
        for keyword, ctx in context_map[fname].items():
            if keyword in cmd_lower:
                return ctx

    # Fallback: function-name based context detection
    # (used when cmd template is unresolvable, e.g. <raw_clone_template>)
    fn_lower = function_name.lower()
    if fname == "lfwrite.py":
        if "raw_clone" in fn_lower:
            return "RAW_CLONE_MAP dispatch (securakey/gallagher/paradox/nexwatch)"
        if "raw_t55" in fn_lower:
            return "T55xx block write"
        if "raw" in fn_lower and "write" in fn_lower:
            return "T55xx block write"
        if "b0_need" in fn_lower:
            return "T55xx block write"
        if "dump_em4x05" in fn_lower:
            return "EM4x05 block write"
        if "block_em4x05" in fn_lower:
            return "EM4x05 block write"
        if "hitag2" in fn_lower or "paxton" in fn_lower:
            return "Hitag2/Paxton"
        if "nedap" in fn_lower:
            return "NEDAP clone (T5577)"

    if cmd_lower.startswith("lf sea") or cmd_lower.startswith("lf search"):
        if "paxton" in fn_lower or "hitag2" in fn_lower:
            return "LF hitag2/paxton presence check"
        if "inline_verify" in fn_lower or "verify" in fn_lower:
            return "LF verify presence check"
        return "LF search scan"

    if cmd_lower.startswith("data save"):
        return "LF waveform capture"

    if cmd_lower.startswith("lf t55xx"):
        return "T55xx command"

    if fname == "hfmfwrite.py":
        if "cload" in cmd_lower:
            return "Gen1a cload (dump restore)"
        if "csetuid" in cmd_lower:
            return "Gen1a csetuid (UID force-set)"
        if "wrbl" in cmd_lower:
            return "MIFARE Classic block write"
        if "cgetblk" in cmd_lower:
            return "MIFARE Classic block read (probe)"
        if "14a info" in cmd_lower:
            return "HF 14A info (card presence)"
        if "14a raw" in cmd_lower:
            return "Gen1a freeze sequence (raw)"

    if fname == "hfmfuwrite.py":
        if "mfu restore" in cmd_lower:
            return "MFU restore (Ultralight/NTAG)"
        if "mfu info" in cmd_lower:
            return "MFU info (magic card detection)"

    if fname == "iclasswrite.py":
        if "calcnewkey" in cmd_lower:
            return "iCLASS key calculation"
        if "wrbl" in cmd_lower:
            return "iCLASS block write"
        if "rdbl" in cmd_lower:
            return "iCLASS block read"

    if fname == "scan.py":
        if "14a info" in cmd_lower:
            return "HF 14A scan"
        if "hf sea" in cmd_lower:
            return "HF search scan"
        if cmd_lower.startswith("lf sea"):
            return "LF search scan"
        if "hitag read" in cmd_lower:
            return "Hitag2/Paxton probe"
        if "felica" in cmd_lower:
            return "FeliCa scan"
        if "mfu info" in cmd_lower:
            return "Ultralight/NTAG scan"
        if "data save" in cmd_lower:
            return "LF waveform capture"

    if fname == "lfverify.py":
        if cmd_lower.startswith("lf sea"):
            return "LF verify presence check"

    if fname == "write.py":
        return "Write dispatcher (no direct PM3 commands)"

    return "Unknown"


def classify_category(filepath, function_name, cmd):
    """Determine which output category a command belongs to."""
    fname = os.path.basename(filepath)
    cmd_lower = cmd.lower().strip()

    if fname in ("lfwrite.py", "lfverify.py"):
        if "hitag" in cmd_lower or ("paxton" in function_name.lower()):
            return 4
        return 1

    if fname == "hfmfwrite.py":
        return 2

    if fname == "hfmfuwrite.py":
        return 3

    if fname == "iclasswrite.py":
        return 5

    if fname == "scan.py":
        if "felica" in cmd_lower:
            return 5
        if "mfu" in cmd_lower:
            return 3
        if "14a" in cmd_lower:
            return 2
        if "hf sea" in cmd_lower:
            if "isclass" in function_name.lower() or "mifare" in function_name.lower():
                return 2
            return 5
        if cmd_lower.startswith("lf sea") or "data save" in cmd_lower:
            return 1
        if cmd_lower.startswith("lf t55xx"):
            return 1
        return 1

    if fname == "write.py":
        return 1

    return 1


RESPONSE_PARSERS = {
    ("scan.py", "scan_14a"): "hf14ainfo.parser() + hasKeyword('NTAG 213'/'NTAG 215'/'Ultralight C'/...)",
    ("scan.py", "scan_hfsea"): "hfsearch.parser() + hasKeyword('isIclass'/'isMifare')",
    ("scan.py", "scan_lfsea"): "lfsearch.parser() + hasKeyword('isT55XX'/'isHitag2'/'isEm4x05')",
    ("scan.py", "scan_hitag_paxton"): "hasKeyword('Paxton id...') + regex REX_PAXTON_HEX + REX_HITAG2_BLOCK",
    ("scan.py", "scan_t55xx"): "lft55xx.DUMP_TEMP cached dict",
    ("scan.py", "scan_em4x05"): "lfem4x05.infoAndDumpEM4x05ByKey() cached",
    ("scan.py", "scan_felica"): "hffelica.parser()",
    ("scan.py", "lf_wav_filter"): "Direct file read /tmp/lf_trace_tmp.pm3 + amplitude >= 90",

    ("lfwrite.py", "write_em410x"): "startPM3Task return code (ret == -1 check)",
    ("lfwrite.py", "write_hid"): "startPM3Task return code",
    ("lfwrite.py", "write_indala"): "startPM3Task return code",
    ("lfwrite.py", "write_fdx_par"): "startPM3Task return code",
    ("lfwrite.py", "write_keri"): "startPM3Task return code",
    ("lfwrite.py", "write_nedap"): "startPM3Task return code",
    ("lfwrite.py", "write_raw_clone"): "startPM3Task return code",
    ("lfwrite.py", "write_raw_t55xx"): "startPM3Task return code",
    ("lfwrite.py", "write_b0_need"): "startPM3Task (fire-and-forget)",
    ("lfwrite.py", "write_dump_t55xx"): "startPM3Task rc + lft55xx.DUMP_TEMP + regex '^\\s*\\d+\\s*\\| ([A-Fa-f0-9]{8})\\s*|'",
    ("lfwrite.py", "write_block_em4x05"): "startPM3Task return code",
    ("lfwrite.py", "write_dump_em4x05"): "regex 'Address\\s+\\d+\\s+\\|\\s+([A-Fa-f0-9]{8})\\s+-' or fallback '|\\s+([A-Fa-f0-9]{8})\\s+-'",
    ("lfwrite.py", "write_paxton_blocks"): "hasKeyword('Valid Paxton ID found!') + startPM3Task return code",
    ("lfwrite.py", "write_hitag2_blocks"): "hasKeyword('Paxton id...') (reject) + hasKeyword + isEmptyContent() + startPM3Task return code",
    ("lfwrite.py", "_inline_verify"): "lf sea + lfread.READ[typ](save=False) (best-effort, result not checked)",
    ("lfwrite.py", "check_detect"): "Delegates to lft55xx.wipe_t() + lft55xx.detectT55XX() + lft55xx.chkT55xx()",

    ("hfmfwrite.py", "start_wrbl_cmd"): "N/A - builds template only",
    ("hfmfwrite.py", "write_block"): "hasKeyword(r'Write \\( ok \\)')",
    ("hfmfwrite.py", "gen1afreeze"): "No response check (fire-and-forget 5 raw commands)",
    ("hfmfwrite.py", "_normalize_gen1a_sak"): "regex 'UID:\\s*([0-9A-Fa-f ]+)' + hasKeyword(\"Can't set UID\") + 'new block 0[.\\s]*([0-9A-Fa-f]{32})'",
    ("hfmfwrite.py", "write_with_gen1a"): "hasKeyword(\"Can't set magic\") + hasKeyword('Card loaded')",
    ("hfmfwrite.py", "write_with_gen1a_only_uid"): "hasKeyword(\"Can't set UID\")",
    ("hfmfwrite.py", "write_with_standard"): "hasKeyword(r'Write \\( ok \\)') per block",
    ("hfmfwrite.py", "write_common"): "hasKeyword('UID') for presence + hasKeyword error keywords for gen1a detect",
    ("hfmfwrite.py", "verify"): "regex 'UID:\\s*([\\dA-Fa-f ]+)' + Gen1a block regex + verify_gen2 block count",

    ("hfmfuwrite.py", "write"): "hasKeyword(_KW_SELECT_FAIL=\"Can't select card\") + hasKeyword(_KW_RESTORE_SUCCESS='Done!') + regex 'failed to write block\\s+(\\d+)' (blk < 241 = fail)",
    ("hfmfuwrite.py", "verify"): "scan.scan_14a() + scan.isTagFound() + UID comparison",

    ("iclasswrite.py", "calcNewKey"): "regex r'Xor div key\\.+\\s+([0-9A-Fa-f ]+)'",
    ("iclasswrite.py", "writeDataBlock"): "hasKeyword(r'\\( ok \\)')",
    ("iclasswrite.py", "writeDataBlocks"): "writeDataBlock return code (== 0)",
    ("iclasswrite.py", "write"): "writeDataBlocks return code + verify dispatch",
    ("iclasswrite.py", "verify"): "regex r'block\\s+\\d+\\s*/0x[0-9A-Fa-f]+\\s*:\\s+([A-Fa-f0-9 ]+)' + data comparison",

    ("lfverify.py", "verify_t55xx"): "lft55xx.dumpT55XX_Text() + regex '^\\s*\\d+\\s*\\| ([A-Fa-f0-9]{8})\\s*|' + .bin file compare",
    ("lfverify.py", "verify_em4x05"): "lfem4x05.readBlocks() + regex 'Address\\s+\\d+\\s+\\|\\s+([A-Fa-f0-9]{8})\\s+-'",
    ("lfverify.py", "verify"): "scan.scan_lfsea() + scan.isTagFound() + lfread.READ[typ](save=False) + UID/raw comparison",

    ("write.py", "write"): "call_on_finish(listener) dispatch based on return code",
    ("write.py", "verify"): "call_on_finish(listener) dispatch based on return code",
}


def get_response_parser(filepath, function_name):
    """Look up the response parser for a given file+function."""
    fname = os.path.basename(filepath)
    key = (fname, function_name)
    return RESPONSE_PARSERS.get(key, "startPM3Task return code only")


def check_pm3_compat_imported(tree, source_text):
    """Check if the module imports pm3_compat (uses AST + regex fallback)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                full_name = alias.name if isinstance(node, ast.Import) else (node.module or "")
                if "pm3_compat" in str(full_name):
                    return True
            if isinstance(node, ast.ImportFrom) and node.module and "pm3_compat" in node.module:
                return True
    # Fallback: regex search in source
    if re.search(r'import\s+pm3_compat|from\s+.*pm3_compat\s+import|from\s+\.+\s+import\s+pm3_compat', source_text):
        return True
    return False


def get_line_for_node(node):
    """Get line number from a node, handling different node types."""
    if hasattr(node, "lineno"):
        return node.lineno
    return -1


def extract_from_source_fallback(source_lines, var_map, cmd_node, line_no,
                                  enclosing_fn, module_vars, func_vars, loop_vars, tree):
    """Fallback: scan source lines before the dispatch point to find cmd assignment.

    When AST-based template extraction fails (e.g. complex loop/conditional
    patterns), this function walks backwards from the dispatch line to find
    the most recent `cmd = ...` or `ret = ...` assignment and extracts the
    command string from the source text directly.
    """
    if not source_lines:
        return "<dynamic/unresolvable>"

    # Get the variable name being passed to startPM3Task
    if isinstance(cmd_node, ast.Name):
        var_name = cmd_node.id
    elif isinstance(cmd_node, ast.Constant) and isinstance(cmd_node.value, str):
        return cmd_node.value
    elif isinstance(cmd_node, ast.JoinedStr):
        return extract_command_template(cmd_node, var_map, tree)
    else:
        return "<dynamic/unresolvable>"

    # Walk backwards from the dispatch line to find the variable assignment
    for i in range(line_no - 2, -1, -1):
        if i >= len(source_lines):
            continue
        line = source_lines[i]
        stripped = line.strip()
        # Look for: var_name = <something>
        pattern = re.compile(rf'^\s*{re.escape(var_name)}\s*=\s*(.+)$')
        match = pattern.match(stripped)
        if match:
            rhs = match.group(1)
            # Build a clean command template from the source text
            template = rhs

            # Remove .format() suffix and its arguments
            template = re.sub(r'\.format\([^)]*\)', '', template)
            # Remove .upper() suffix
            template = re.sub(r'\.upper\(\)', '', template)
            # Remove string concatenation operators and clean up spacing
            template = re.sub(r'\s*\+\s*', ' ', template)
            # Remove RAW_CLONE_MAP dictionary lookup artifacts
            template = re.sub(r'RAW_CLONE_MAP\[[^\]]+\]', '<raw_clone_template>', template)
            # Normalize whitespace
            template = re.sub(r'\s+', ' ', template).strip()

            # Clean up quotes around the whole expression
            template = template.strip()
            while (template.startswith("'") and template.endswith("'")) or \
                  (template.startswith('"') and template.endswith('"')):
                template = template[1:-1].strip()

            # Remove leading quote artifact (e.g. "'data save -f ' FILE_BASE")
            template = re.sub(r"^'(?=\S)", "", template)
            template = re.sub(r'^"(?=\S)', "", template)
            # Remove trailing quote artifact
            template = re.sub(r"(?<=\S)'$", "", template)
            template = re.sub(r'(?<=\S)"$', "", template)

            # Remove internal quote artifacts from concatenation (e.g. "data save -f ' FILE_BASE")
            template = re.sub(r"'", "", template)
            template = re.sub(r'"', "", template)
            # Final whitespace normalization
            template = re.sub(r'\s+', ' ', template).strip()

            return template

    return "<dynamic/unresolvable>"


def audit_file(filepath):
    """Audit a single Python file, collecting all PM3 command dispatches."""
    commands = []

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    source_lines = source.splitlines()
    tree = ast.parse(source, filename=filepath)
    module_vars, func_vars, loop_vars = build_function_scoped_var_maps(tree)
    pm3_compat_imported = check_pm3_compat_imported(tree, source)

    for node in ast.walk(tree):
        call_info = is_pm3_dispatch_call(node)
        if call_info:
            func_name, cmd_node, is_compat = call_info
            line_no = get_line_for_node(node)
            enclosing_fn = find_enclosing_function(tree, node)

            # Build line-scoped variable map for this dispatch point
            if enclosing_fn and enclosing_fn in func_vars:
                var_map = build_line_scoped_var_map(
                    func_vars[enclosing_fn], module_vars, line_no
                )
            else:
                var_map = build_line_scoped_var_map({}, module_vars, line_no)

            # Add loop variable bindings
            if enclosing_fn and enclosing_fn in loop_vars:
                for loop_var, (loop_start, loop_end, iter_node) in loop_vars[enclosing_fn].items():
                    if loop_start <= line_no <= loop_end:
                        var_map[loop_var] = iter_node

            cmd_template = extract_command_template(cmd_node, var_map, tree)

            # Fallback: if template is still unresolved, try source-text extraction
            if cmd_template.startswith("<") and cmd_template.endswith(">"):
                cmd_template = extract_from_source_fallback(
                    source_lines, var_map, cmd_node, line_no, enclosing_fn,
                    module_vars, func_vars, loop_vars, tree
                )

            if not cmd_template:
                cmd_template = "<dynamic/unresolvable>"

            card_context = classify_card_context(filepath, enclosing_fn or "<module>", cmd_template)
            category = classify_category(filepath, enclosing_fn or "<module>", cmd_template)
            parser = get_response_parser(filepath, enclosing_fn or "<module>")

            if is_compat:
                dispatch_type = "pm3_compat.translate"
            elif "translate" in func_name.lower():
                dispatch_type = "pm3_compat.translate"
            else:
                dispatch_type = "executor.startPM3Task"

            commands.append({
                "file": filepath,
                "line": line_no,
                "function": enclosing_fn or "<module>",
                "command": cmd_template,
                "card_context": card_context,
                "category": category,
                "dispatch": dispatch_type,
                "routed_through_pm3_compat": is_compat,
                "module_imports_pm3_compat": pm3_compat_imported,
                "response_parser": parser,
            })

    return commands, pm3_compat_imported


CATEGORY_HEADERS = {
    1: "Category 1: LF Clone Writes & Verifications (T5577 targets)",
    2: "Category 2: HF Mifare Classic (Gen1a vs Standard/Gen2)",
    3: "Category 3: HF Ultralight / NTAG",
    4: "Category 4: LF Hitag2 / Paxton",
    5: "Category 5: HF iCLASS & ISO15693",
}


def print_inventory(commands):
    """Print the structured command inventory grouped by category."""
    print("=" * 140)
    print("PM3 COMMAND & PARSER INVENTORY")
    print("Source: release/extracted-955/lib/ (Extracted v9.5.5)")
    print("Target: Proxmark3 v4.23346 (Iceman)")
    print("=" * 140)
    print()

    # pm3_compat import status
    print("pm3_compat.py Import Status:")
    print("-" * 70)
    files_checked = set()
    for cmd in commands:
        fname = os.path.basename(cmd["file"])
        if fname in files_checked:
            continue
        files_checked.add(fname)
        status = "IMPORTS pm3_compat" if cmd["module_imports_pm3_compat"] else "NO pm3_compat import"
        print(f"  {fname:<22s} -> {status}")
    print()

    # Total counts
    direct = [c for c in commands if not c["routed_through_pm3_compat"]]
    compat = [c for c in commands if c["routed_through_pm3_compat"]]
    print(f"Total PM3 dispatch points: {len(commands)}")
    print(f"  Direct (executor.startPM3Task):  {len(direct)}")
    print(f"  Routed through pm3_compat:       {len(compat)}")
    print()

    # Group by category
    print("All PM3 Command Dispatch Inventory:")
    print("-" * 140)

    for cat_num in range(1, 6):
        cat_cmds = [c for c in commands if c["category"] == cat_num]
        if not cat_cmds:
            continue

        print()
        print(CATEGORY_HEADERS[cat_num])
        print("-" * 140)

        by_file = {}
        for cmd in cat_cmds:
            fname = os.path.basename(cmd["file"])
            if fname not in by_file:
                by_file[fname] = []
            by_file[fname].append(cmd)

        for fname, file_cmds in sorted(by_file.items()):
            print(f"\n  File: {fname}")
            for cmd in file_cmds:
                print(f"    L{cmd['line']:>5d}  Fn: {cmd['function']:<32s}  Dispatch: {cmd['dispatch']}")
                print(f"{'':60s}Context: {cmd['card_context']}")
                print(f"{'':60s}Cmd:     {cmd['command'][:100]}")
                if len(cmd["command"]) > 100:
                    print(f"{'':60s}          ... {cmd['command'][100:]}")
                parser = cmd["response_parser"]
                if len(parser) > 110:
                    parser = parser[:107] + "..."
                print(f"{'':60s}Parser:  {parser}")

    # Unique command templates
    print()
    print("=" * 140)
    print("UNIQUE COMMAND TEMPLATES (de-duplicated by pattern)")
    print("=" * 140)

    seen_templates = {}
    for cmd in commands:
        norm = re.sub(r'\{[^}]+\}', '{...}', cmd["command"])
        if norm not in seen_templates:
            seen_templates[norm] = cmd
    for norm, cmd in sorted(seen_templates.items(), key=lambda x: x[0]):
        print(f"  [{cmd['category']}] {os.path.basename(cmd['file'])}:{cmd['function']} -> {norm}")

    print()
    print("=" * 140)
    print("SUMMARY")
    print("=" * 140)
    print(f"  Total dispatch points:    {len(commands)}")
    print(f"  Direct dispatches:        {len(direct)}")
    print(f"  pm3_compat-routed:        {len(compat)}")
    print()

    print("Commands by category:")
    for cat_num in range(1, 6):
        count = len([c for c in commands if c["category"] == cat_num])
        print(f"  {CATEGORY_HEADERS[cat_num]}: {count} dispatch points")


def main():
    lib_dir = os.path.join(TARGET_DIR)

    if not os.path.isdir(lib_dir):
        print(f"ERROR: Directory not found: {lib_dir}")
        sys.exit(1)

    all_commands = []

    for fname in TARGET_FILES:
        filepath = os.path.join(lib_dir, fname)
        if not os.path.isfile(filepath):
            print(f"WARNING: File not found: {filepath}")
            continue
        commands, compat_imported = audit_file(filepath)
        all_commands.extend(commands)

    print_inventory(all_commands)


if __name__ == "__main__":
    main()
