# OpenCodexSinicization

对中文圈流传的两个 Codex 相关工具的反编译与安全分析。

**本仓库是安全研究性质的披露仓库，不是这两个工具的分发渠道，也不建议任何人使用它们。**

> README 正在撰写中。

---

## 仓库内容

```
app/                    反编译还原的工具自身源码（唯一自有业务代码）
  main.py                 主程序：密钥验证 / 启动内置 Xray / 改写系统代理
  pyimod0*.py             PyInstaller 运行时文件（原版，未改动）
  pyi_rth_*.py            PyInstaller 运行时钩子（原版，未改动）
  struct.py               标准库 shim
assets/                 从可执行文件中提取的原始资源
  node.txt                内置 VLESS/Reality 节点（**凭据已打码**，见下）
  vendor/xray/xray.exe    内置代理内核（上游第三方二进制，Xray-core）
stdlib_python314/       打包进去的 142 个 Python 3.14 标准库模块（参考件）
_analysis/              反编译校验证据
  main.disasm.txt         CPython 3.14 官方反汇编
  _VERIFICATION.txt       逐模块校验报告
  *.flow.txt              关键函数的指令级控制流
反编译报告.md              还原过程与质量校验说明
安全审计报告.md            完整审计结论
```

## 关于 `assets/node.txt`

该文件原文包含一个**可直接使用的** VLESS/Reality 代理凭据。
发布时已把凭据部分替换为占位符，只保留 URL 形状与服务器地址，用于证明
"该工具硬编码了一个第三方节点"这一事实：

```
vless://<REDACTED-UUID>@154.201.74.158:443?encryption=none&flow=xtls-rprx-vision
  &fp=chrome&pbk=<REDACTED-PUBLIC-KEY>&security=reality&sid=<REDACTED-SHORT-ID>
  &sni=www.cloudflare.com&spx=<REDACTED-SPX>&type=tcp
```

打码不影响任何结论：节点地址、协议、SNI 伪装目标、以及"凭据硬编码在文件里"
这一事实，全部保留。

## 复现

```powershell
# 1) 解析 PyInstaller CArchive
python extract_carchive.py "Codex中文汉化工具-Windows.exe" extracted

# 2) 解包 PYZ（zlib + marshal，与宿主 Python 版本无关）
python extract_pyz.py extracted\PYZ.pyz.raw extracted\PYZ

# 3) 用支持 3.14 的反编译器还原为源码
python decompile_all.py

# 4) 用 CPython 3.14 官方反汇编做权威校验
python authoritative_disasm.py extracted\main.raw main.disasm.txt
```

校验方法：还原出的 9 个文件全部能用 CPython 3.14.0 编译通过，
并且 `main.py` 的每个函数、每个字符串常量都与官方 `dis` 反汇编逐条比对一致。

## 目标文件指纹

| 文件 | 大小 | 编译时间戳 | 栈 |
|---|---|---|---|
| `Codex中文汉化工具-Windows.exe` | 25,840,440 B | 2026-10-01 12:48 | Python 3.14 + PyInstaller |
| `Codex助手2.1.1-Windows.exe` | 71,906,824 B | 2026-08-20 21:04 | .NET 8 单文件 + WinForms |

两个文件**均无数字签名**。

## 立场说明

- 本仓库只做**行为披露与技术分析**。
- 反编译产物中的程序权利归原作者；本仓库不主张任何权利。
- 仓库不提供可用于运行的破解版，也不指导如何绕过任何验证。
- 已移除所有可直接使用的第三方代理凭据。
- 若权利人认为本仓库内容不当，请通过 Issue 联系，会配合处理。
