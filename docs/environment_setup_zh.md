# Windows 环境安装说明

本文用于补齐 `plan.md` 要求但当前环境中缺少的工具。安装完成后，必须重新打开 PowerShell，使新的 `PATH` 生效。

## 1. 必需工具

| 工具 | 用途 | 验证命令 |
| --- | --- | --- |
| Icarus Verilog | Verilog-2005 单元仿真 | `iverilog -V` |
| Verilator | Verilog-2005 lint 和整机仿真 | `verilator --version` |
| GTKWave | 查看 VCD/FST 波形 | `gtkwave --version` |
| Yosys | RTL 综合和结构检查 | `yosys --version` |
| RISC-V GNU GCC/Binutils | 编译 RV32I/RV32IM 测试程序 | `riscv64-elf-gcc --version` |

Git、GNU Make、CMake 和 Python 已经存在时，不需要重复安装；仍建议使用下方命令确认版本。

## 2. HDL 工具安装

### 方案 A：OSS CAD Suite

OSS CAD Suite 是最方便的打包方式，通常同时包含 Icarus Verilog、Verilator、GTKWave 和 Yosys。

1. 打开 <https://github.com/YosysHQ/oss-cad-suite-build/releases>。
2. 下载最新的 `oss-cad-suite-windows-x64-*.tgz`。
3. 使用 7-Zip 或 Windows `tar` 解压到不含空格的目录，例如：

   ```powershell
   C:\tools\oss-cad-suite
   ```

   如果 `.tgz` 先解出一个 `.tar` 文件，再对 `.tar` 解压一次即可。

4. 将以下目录加入系统或用户 `PATH`：

   ```text
   C:\tools\oss-cad-suite\bin
   ```

5. 重新打开 PowerShell，并执行：

   ```powershell
   iverilog -V
   verilator --version
   yosys --version
   gtkwave --version
   ```

如果下载速度过慢，可以改用下面的独立安装方式；不要同时把多个版本的同名工具放在 `PATH` 前面，以免版本混用。

### 方案 B：MSYS2

1. 从 <https://www.msys2.org/> 安装 MSYS2。
2. 在 **MSYS2 UCRT64** 终端执行：

   ```bash
   pacman -Syu
   ```

   按提示关闭并重新打开终端，然后再次执行：

   ```bash
   pacman -Su
   pacman -S --needed mingw-w64-ucrt-x86_64-iverilog \
       mingw-w64-ucrt-x86_64-verilator \
       mingw-w64-ucrt-x86_64-gtkwave \
       mingw-w64-ucrt-x86_64-yosys
   ```

3. 将 `C:\msys64\ucrt64\bin` 加入 Windows `PATH`。

不同 MSYS2 镜像的包名可能变化。如果 `pacman` 报包不存在，请在 MSYS2 中运行 `pacman -Ss iverilog`、`pacman -Ss verilator` 和 `pacman -Ss yosys`，选择对应的 UCRT64 包。

### 方案 C：独立 Windows 安装包

也可以从各项目的官方发布页分别安装：

- Icarus Verilog：<https://github.com/steveicarus/iverilog/releases>
- Verilator：<https://github.com/verilator/verilator/releases>
- GTKWave：<https://gtkwave.sourceforge.net/>
- Yosys：<https://github.com/YosysHQ/yosys/releases>

安装后将每个程序所在目录加入 `PATH`，然后执行上面的四条验证命令。只使用官方发布页或可信的包管理器，不要下载来历不明的预编译包。

## 3. RISC-V GNU 工具链

项目需要支持以下编译选项：

```text
-march=rv32i  -mabi=ilp32
-march=rv32im -mabi=ilp32
```

优先安装包含 multilib 的 **riscv64-elf GCC/Binutils**，并确认它能生成 RV32I/RV32IM。可选择：

- xPack RISC-V Embedded GCC：<https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases>
- RISC-V GNU Toolchain 官方构建说明：<https://github.com/riscv-collab/riscv-gnu-toolchain>
- MSYS2 中可用的 RISC-V 交叉编译包（若当前仓库提供）：在 MSYS2 中执行 `pacman -Ss riscv` 查询。

安装后将包含 `gcc.exe`、`objdump.exe`、`objcopy.exe` 等程序的 `bin` 目录加入 `PATH`。不同发行版的前缀可能是 `riscv64-unknown-elf-`，而计划使用的是 `riscv64-elf-`。两者不能混写；若实际前缀不同，请在项目命令或 Makefile 中设置相应的 `RISCV_PREFIX`，例如：

```powershell
$env:RISCV_PREFIX = "riscv64-unknown-elf-"
```

确认编译器和 Binutils 均可用：

```powershell
riscv64-elf-gcc --version
riscv64-elf-objdump --version
riscv64-elf-objcopy --version
riscv64-elf-gcc -print-multi-lib | Select-String "rv32|ilp32"
```

如果最后一条命令没有输出，说明当前 GCC 没有提供项目需要的 RV32 multilib，应更换工具链。

如果安装的是 `riscv64-unknown-elf-` 前缀，将上面命令中的前缀全部替换为实际前缀。

## 4. PowerShell PATH 配置

下面的命令只修改当前 PowerShell 会话，适合先验证安装结果：

```powershell
$env:Path = "C:\tools\oss-cad-suite\bin;C:\riscv\bin;" + $env:Path
```

确认无误后，可以通过 Windows 的“系统属性 -> 环境变量”永久添加目录。不要覆盖原有 `PATH`，只需在前面追加工具目录。

## 5. 一次性环境检查

在仓库根目录 `E:\Verilog_cpu` 打开新的 PowerShell，执行：

```powershell
$tools = @(
  "git", "make", "cmake", "python", "iverilog",
  "verilator", "gtkwave", "yosys", "riscv64-elf-gcc",
  "riscv64-elf-objdump", "riscv64-elf-objcopy"
)
foreach ($tool in $tools) {
  $cmd = Get-Command $tool -ErrorAction SilentlyContinue
  if ($cmd) { "OK      $tool -> $($cmd.Source)" }
  else { "MISSING $tool" }
}
```

所有工具都显示 `OK` 后，再运行：

```powershell
make doctor
make lint
```

`make doctor` 或 `make lint` 出现错误时，应先修复环境或 PATH，不能跳过错误继续执行 PART-01。Icarus 使用 `-g2005`，Verilator 使用 `--language 1364-2005`，Yosys 使用 Verilog 读取模式；这些选项是本项目 Verilog-2005 约束的一部分。

## 6. 常见问题

- **命令找不到**：重新打开终端，执行 `Get-Command <命令>`，检查实际目录是否在 `PATH` 中。
- **找到了错误版本**：执行 `Get-Command <命令> -All`，将项目要求的版本目录放在 `PATH` 最前面。
- **RISC-V 编译器不支持 `rv32im/ilp32`**：重新安装带 multilib 的发行版；仅能编译 RV64 的工具链不满足要求。
- **Windows `timeout` 行为不同**：项目命令在 GNU Make 环境中使用超时控制；如果后续 Makefile 无法调用 GNU coreutils `timeout`，请安装 MSYS2 coreutils，并确保其 `bin` 目录位于 `PATH` 中。
- **权限错误**：工具安装目录不要放在受保护的系统目录；可使用 `C:\tools` 或用户目录，并以管理员权限安装需要系统写入的组件。
