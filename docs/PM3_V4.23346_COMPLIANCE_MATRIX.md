=================================================================
PM3 v4.23346 CLI COMPLIANCE MATRIX
Empirical validation of AutoCopy dispatched commands
against Proxmark3 v4.23346 source tree
(ProxSpace-master\pm3\proxmark3\client\src\)
=================================================================

Binary location: D:\proxspace\ProxSpace-master\pm3\proxmark3\client\proxmark3.exe
Binary version:  Proxmark3 v4.23346 (git: fc024c803)
Source tag:      v4.23346
Binary execution: FAILED (STATUS_ILLEGAL_INSTRUCTION / exit code -1073741511)
Source verification: PASSED (all CLIParserInit + argtable definitions confirmed)

=================================================================
COMPLIANCE MATRIX
=================================================================

| # | Command in AutoCopy | PM3 v4.23346 CLI Spec | Match | Delta/ Notes |
|---|---------------------|----------------------|-------|--------------|
| 1 | lf sea | lf search (prefix match) | YES | "sea" is prefix of "search" in command table cmdlf.c:2452 |
| 2 | hf sea | hf search (prefix match) | YES | "sea" is prefix of "search" in command table cmdhf.c:678 |
| 3 | lf em 410x clone --id {id} | lf em 410x clone | YES | --id is arg_str1(NULL,"id",...) cmdlfem410x.c:637. Required field confirmed |
| 4 | lf hid clone -r {id} | lf hid clone | YES | -r/--raw is arg_str0("r","raw",...) cmdlfhid.c:425 |
| 5 | lf indala clone -r {raw} | lf indala clone | YES | -r/--raw is arg_str0("r","raw",...) cmdlfindala.c:800 |
| 6 | lf fdxb clone --country {} --national {} | lf fdxb clone | YES | --country arg_u64_1("c","country") cmdlffdxb.c:722, --national arg_u64_1("n","national") cmdlffdxb.c:723 |
| 7 | lf keri clone -t i --cn {id} | lf keri clone | YES | -t/--type arg_str0("t","type",...) cmdlfkeri.c:238, --cn arg_int1(NULL,"cn",...) cmdlfkeri.c:240. Required field |
| 8 | lf t55xx write -b 0 -d {b0} | lf t55xx write | YES | -b/--blk arg_int1("b","blk") cmdlft55xx.c:3148, -d/--data arg_str0("d","data") cmdlft55xx.c:3149. Both valid |
| 9 | lf t55xx write -b {} -d {} -p {} | lf t55xx write | YES | -k/--pwd arg_str0("p","pwd",...) cmdlft55xx.c:3150 |
| 10 | lf t55xx restore -f {file} | lf t55xx restore | YES | -f/--file arg_str0("f","file",...) cmdlft55xx.c:3944 |
| 11 | lf hitag read --ht2 -k {key} | lf hitag read | YES | --ht2 arg_lit0("2","ht2") cmdlfhitag.c:1032, -k/--key arg_str0("k","key",...) cmdlfhitag.c:1036 |
| 12 | lf hitag wrbl --ht2 -p {} -d {} -k {key} | lf hitag wrbl | YES | --ht2 arg_lit0("2","ht2") cmdlfhitag.c:1269, -p/--page arg_int1("p","page") cmdlfhitag.c:1274, -d/--data arg_str1("d","data") cmdlfhitag.c:1275, -k/--key arg_str0("k","key") cmdlfhitag.c:1273. All valid |
| 13 | lf search | lf search | YES | Registered at cmdlf.c:2452, args: -1, -c, -u |
| 14 | lf securakey clone -r {raw} | lf securakey clone | YES | -r/--raw arg_str1("r","raw",...) cmdlfsecurakey.c:181. Required field |
| 15 | lf gallagher clone -r {raw} | lf gallagher clone | YES | -r/--raw arg_str0("r","raw",...) cmdlfgallagher.c:185 |
| 16 | lf paradox clone -r {raw} | lf paradox clone | YES | -r/--raw arg_str0("r","raw",...) cmdlfparadox.c:306 |
| 17 | lf nexwatch clone -r {raw} | lf nexwatch clone | YES | -r/--raw arg_str0("r","raw",...) cmdlfnexwatch.c:308 |
| 18 | lf em 4x05 read -a {addr} | lf em 4x05 read | YES | -a/--addr arg_int1("a","addr",...) cmdlfem4x05.c:1344. Required field |
| 19 | lf em 4x05 write -a {addr} -d {data} -p {key} | lf em 4x05 write | YES | -a/--addr arg_int0("a","addr") cmdlfem4x05.c:1391, -d/--data arg_str1("d","data") cmdlfem4x05.c:1392, -p/--pwd arg_str0("p","pwd") cmdlfem4x05.c:1393 |
| 20 | data save -f {file_base} | data save | YES | -f/--file arg_str1("f","file",...) cmddata.c:2221 |
| 21 | hf mf wrbl --blk {block} {-a|-b} -k {key} -d {data} --force | hf mf wrbl | YES | --blk arg_int1(NULL,"blk") cmdhfmf.c:1369, -a arg_lit0("a") cmdhfmf.c:1370, -b arg_lit0("b") cmdhfmf.c:1371, -k/--key arg_str0("k","key") cmdhfmf.c:1374, -d/--data arg_str0("d","data") cmdhfmf.c:1375, --force arg_lit0(NULL,"force") cmdhfmf.c:1373. All valid |
| 22 | hf 14a info | hf 14a info | YES | -v, -n, -s flags exist cmdhf14a.c:993-997 |
| 23 | hf 14a raw {-flags} {hex} (5 variants) | hf 14a raw | YES | -a, -c, -k, -b, -3, -r, -s, -t, -v, -w, --topaz, --crypto1, --schann all valid cmdhf14a.c:1849-1864 |
| 24 | hf mf csetuid -u {uid} --atqa {atqa} --sak {sak} | hf mf csetuid | YES | -u/--uid arg_str0("u","uid") cmdhfmf.c:5972, --atqa arg_str0("a","atqa") cmdhfmf.c:5973, --sak arg_str0("s","sak") cmdhfmf.c:5974, -w/--wipe arg_lit0("w","wipe") cmdhfmf.c:5971 |
| 25 | hf mf cload -f {file} | hf mf cload | YES | -f/--file arg_str0("f","file") cmdhfmf.c:6163 |
| 26 | hf mf cgetblk --blk 0 | hf mf cgetblk | YES | --blk arg_int1("b","blk") cmdhfmf.c:6346 |
| 27 | hf mfu restore {flags} -f {file} | hf mfu restore | YES | -f/--file arg_str1("f","file") cmdhfmfu.c:4073, -s arg_lit0("s",NULL) cmdhfmfu.c:4076, -k/--key arg_str0("k","key") cmdhfmfu.c:4074, -e arg_lit0("e",NULL) cmdhfmfu.c:4077 |
| 28 | hf mfu info | hf mfu info | YES | -k/--key arg_str0("k","key") cmdhfmfu.c:2559, -l arg_lit0 cmdhfmfu.c:2560, --force arg_lit0 cmdhfmfu.c:2561 |
| 29 | hf iclass calcnewkey --old {} --new {} | hf iclass calcnewkey | YES | --old arg_str0(NULL,"old") cmdhficlass.c:5656, --new arg_str0(NULL,"new") cmdhficlass.c:5658 |
| 30 | hf iclass wrbl --blk {block} -d {data} -k {key} | hf iclass wrbl | YES | --blk arg_int1(NULL,"blk") cmdhficlass.c:3241, -d/--data arg_str1("d","data") cmdhficlass.c:3242, -k/--key arg_str0("k","key") cmdhficlass.c:3239 |
| 31 | hf iclass rdbl --blk {addr} -k {key} | hf iclass rdbl | YES | --blk arg_int1(NULL,"blk") cmdhficlass.c:3735, -k/--key arg_str0("k","key") cmdhficlass.c:3733 |
| 32 | hf felica reader | hf felica reader | YES | -s/--silent arg_lit0 cmdhffelica.c:2696, @ arg_lit0 cmdhffelica.c:2697 |

=================================================================
FLAG COMPATIBILITY DETAILS
=================================================================

### -k flag usage in AutoCopy (verified NOT conflicting with --keep)

AutoCopy uses -k for:
  - lf hitag read --ht2 -k {key}      -> PM3: arg_str0("k","key",...) cmdlfhitag.c:1036  OK
  - lf hitag wrbl --ht2 -p {} -d {} -k {key}  -> PM3: arg_str0("k","key",...) cmdlfhitag.c:1273  OK
  - hf mf wrbl ... -k {key} ...       -> PM3: arg_str0("k","key",...) cmdhfmf.c:1374  OK
  - hf mfu restore -k {key}           -> PM3: arg_str0("k","key",...) cmdhfmfu.c:4074  OK
  - hf mfu info -k {key}              -> PM3: arg_str0("k","key",...) cmdhfmfu.c:2559  OK
  - hf iclass wrbl ... -k {key}       -> PM3: arg_str0("k","key",...) cmdhficlass.c:3239  OK
  - hf iclass rdbl ... -k {key}       -> PM3: arg_str0("k","key",...) cmdhficlass.c:3733  OK

No conflicts found. The -k short flag is consistently used for --key in all
Hitag2, MIFARE Classic, MFU, and iCLASS commands in PM3 v4.23346.

### lf sea / hf sea aliases

lf sea -> matches lf search via CLI prefix matching (cmdlf.c:2452)
hf sea -> matches hf search via CLI prefix matching (cmdhf.c:678)
Both are valid iceman v4.23346 CLI aliases.

### EM4x05 write -p flag (password)

AutoCopy dispatches: lf em 4x05 write -a {addr} -d {data} -p {pwd}
PM3 CLI spec (cmdlfem4x05.c:1389-1396):
  arg_int0("a", "addr", ...)   -- address (0-13)
  arg_str1("d", "data", ...)   -- data (4 hex bytes, REQUIRED)
  arg_str0("p", "pwd", ...)    -- password (4 hex bytes, optional)
MATCH: YES. -p maps to --pwd in PM3 v4.23346.

### EM4x05 read -a flag

AutoCopy dispatches: lf em 4x05 read -a {addr}
PM3 CLI spec (cmdlfem4x05.c:1342-1347):
  arg_int1("a", "addr", ...)   -- address (0-15, REQUIRED)
  arg_str0("p", "pwd", ...)    -- password (optional)
MATCH: YES. -a maps to --addr.

=================================================================
SUMMARY
=================================================================
Total unique command templates checked: 32
Matches: 32
Partial matches: 0
Mismatches: 0
Deprecated/missing flags: 0

COMPLIANCE: PASS (v4.23346)
All AutoCopy dispatched commands are compatible with Proxmark3 v4.23346 CLI specifications.
