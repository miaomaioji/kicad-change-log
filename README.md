# kicad-change-log — KiCad 项目操作日志与变更可视化

[![Version](https://img.shields.io/badge/version-1.1.0-blue)](https://github.com/miaomaioji/kicad-change-log/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Build](https://github.com/miaomaioji/kicad-change-log/actions/workflows/build.yml/badge.svg)](https://github.com/miaomaioji/kicad-change-log/actions/workflows/build.yml)

在 KiCad PCB 编辑器内提供**两个独立窗口**,记录项目快照并把每次改动以
「变动日志 + 图层对比图」的形式可视化。

*Track project snapshots inside the KiCad PCB editor and visualize every
change as a changelog plus layer comparison images.*

## 功能 · Features

### 窗口一:变动日志 · Change Log Window
- 版本时间线(当前板子 + 快照列表),任选两个版本对比
  *Timeline of versions (current board + snapshot list); diff any two.*
- 逐条变更明细:位号 | 变更类型 | 属性 | 变更前 → 变更后
  *Per-item details: reference | change type | attribute | old → new*
  - 例:*e.g.* `X1 坐标变更 (11, 23) → (111, 2222)`
  - 例:*e.g.* `C3 封装变更 Capacitor_SMD:C_0603 → Capacitor_SMD:C_0805`
- 新增 / 删除 / 修改三种类型,颜色区分,类型过滤
  *Added / removed / modified with color coding and type filters.*
- 点击条目显示完整属性级前后对比
  *Click an item for the full attribute-level before/after diff.*
- 走线 / 过孔逐条记录(含网络、层、坐标)
  *Tracks and vias are logged one by one (net, layer, coordinates).*

### 窗口二:变更可视化 · Visualization Window (DRC / JLC DFM style)
- 左侧:按图层分组的变动列表,点击条目 → 图上标记 + 真实板子画布联动定位
  *Left: changes grouped by layer; click to mark on the image and locate on the real canvas.*
- 右侧:`kicad-cli` 渲染的图层对比图,三种模式:
  *Right: layer comparison images rendered by `kicad-cli`, three modes:*
  - **并排对比**:左旧右新
    *Side-by-side: old left, new right*
  - **红绿叠加**:🟢 新增 / 🔴 删除 / 🟡 修改,像素级对齐
    *Overlay: green added / red removed / yellow modified, pixel-aligned*
  - **滑块分割**:拖动滑块分屏查看
    *Slider: drag to split the view*
- 只渲染有变更的图层;对比图可导出 PNG
  *Only changed layers are rendered; comparison image can be exported as PNG.*

### 快照 · Snapshots
- 保存 `.kicad_pcb` 后**自动生成快照**(定时轮询 + 内容 hash 去重),也可手动记录
  *Snapshots are created automatically after saving (polling + content-hash
  dedup), or manually on demand.*
- 快照保存在板文件同目录的 `snapshots/` 下,无需 Git
  *Stored in `snapshots/` next to the board file; no Git required.*

## 安装 · Installation

要求:KiCad 8.0.3 及以上(开发目标 KiCad 10)。
*Requires KiCad 8.0.3+ (developed against KiCad 10).*

```powershell
python install.py
```

脚本会把 `kicad_change_log/` 复制到
`%USERPROFILE%\Documents\KiCad\<版本>\scripting\plugins\`。
*The script copies `kicad_change_log/` into the KiCad scripting plugins folder.*

然后在 KiCad PCB 编辑器中:**工具 → 外部插件 → 刷新插件**,
再点击「项目操作日志与变更可视化」。
*Then in the PCB editor: Tools → External Plugins → Refresh Plugins,
and click "项目操作日志与变更可视化".*

也可以运行 `python build_pcm.py` 生成 PCM 兼容的 zip 包
(或直接从 [Releases](../../releases) 下载)。
*Alternatively run `python build_pcm.py` to build a PCM-compatible zip,
or download one from [Releases](../../releases).*

## 使用说明 · Usage

### 1. 安装与启动 · Setup

```powershell
python install.py
```

打开 KiCad 10 的 PCB 编辑器,**工具 → 外部插件 → 刷新插件**,然后点击
「项目操作日志与变更可视化」(工具栏按钮或插件列表均可)。

也可以 PCM 安装:KiCad 主窗口 → 插件和内容管理器 → 文件安装,
选择 `dist\kicad_change_log_v1.1.0.zip`。

### 2. 日常流程 · Daily Workflow

1. 打开并保存过 `.kicad_pcb` 后运行插件,自动弹出两个窗口,
   并生成第一条「初始快照」;
2. 正常画板,每次保存(Ctrl+S)后约 2 秒自动记录快照(内容无变化不记录);
3. 需要留标记时,在日志窗口点「记录快照」手动记录。

### 3. 变动日志窗口 · Change Log Window

- 运行插件只弹出本窗口;可视化窗口由「打开可视化窗口」按钮呼出
  (并自动继承当前选择的对比版本);
- 顶部选择对比版本 **A(旧)** 与 **B(新)**,默认「倒数第二个快照 vs 当前板子」;
- **实时对比**开关:开启后每 2 秒把当前内存板临时导出,与最近快照实时
  对比,编辑操作即时可见;保存后自动回到与最新快照的对比;
- 三列精简布局(大字号):位号(+/-/~ 符号) | 一行完整变更描述 | 图层;
  颜色:🟢新增(深绿底白字)/ 🔴删除(深红底白字)/ 🟡修改(深黄底黑字);
- 点击某行,下方详情面板显示该元素全部属性级前后对比;
- 「类型过滤」可只看封装 / 走线 / 过孔 / 文本等;
- 按钮:记录快照、在板上高亮、打开可视化窗口;
  被删除的位号会**定位到原位置**并提示原因(元素已不存在于当前板);
- 坐标单位自动跟随板子显示设置(mm / mil)。

### 4. 变更可视化窗口 · Visualization Window (DRC / JLC DFM style)

- **左侧**:变动列表按图层分组(仅显示有变更的图层),
  点击条目 → 对比图上黄色标记 + 真实画布联动定位;
- **右侧**:图层选项卡 + 三种对比模式
  - 并排对比:左旧右新;
  - 红绿叠加:删除=红、新增=绿、修改=黄,未变压暗;
  - 滑块分割:拖动滑块分屏查看;
- **鼠标交互**:滚轮缩放(以光标为中心)、左键拖拽平移、
  双击/中键复位、「适应窗口」按钮一键复位;
- 底部:适应窗口、在板上高亮、导出对比图(PNG)、关闭;
- 渲染在后台线程进行,状态栏显示进度;单个图层约 3~10 秒,
  同版本校准结果自动复用。

### 5. 快照管理 · Snapshot Management

- 快照位于板文件同目录 `snapshots\`,命名 `snap_日期时间_序号.kicad_pcb`,
  `index.json` 记录时间、备注与内容 hash;
- 默认保留最近 200 条,超出自动删除最旧(可在配置中修改);
- 回滚:直接用某个快照文件覆盖当前 `.kicad_pcb`(建议先备份当前文件)。

### 6. 常见问题 · FAQ

| 现象 | 处理 |
|---|---|
| 提示「请先打开并保存一个 PCB 文件」 | 插件需要已保存的板文件路径 |
| 渲染失败 / 未找到 kicad-cli | 在插件目录 `kcl_settings.json` 中设置 `kicad_cli_path` |
| 保存后没有自动快照 | 确认 `auto_snapshot` 为 `true`,且内容确有变化 |
| 板外或超 ±2147 mm 的元素不显示 | KiCad 内部 32 位坐标限制,属正常现象 |
| 两个版本板框差异大 | 红绿叠加中未变元素位置一致但缩放略有差异(固有特性) |

## 配置 · Configuration

编辑 `kcl_settings.json`(插件目录下):
*Edit `kcl_settings.json` (in the plugin folder):*

| 键 | 说明 | 默认 |
|---|---|---|
| `auto_snapshot` | 保存后自动快照 | `true` |
| `snapshot_dir_name` | 快照目录名 | `snapshots` |
| `max_snapshots` | 最多保留快照数 | `200` |
| `poll_interval_s` | 监听轮询间隔(秒) | `2.0` |
| `kicad_cli_path` | kicad-cli 路径(留空自动查找) | `""` |
| `render_width` | 图层图渲染宽度(像素) | `1600` |
| `units_follow_board` | 坐标单位跟随板子设置 | `true` |

## 实现说明 · Implementation Notes

- 纯 Python,无第三方依赖;核心引擎(解析/差异)为纯标准库,见
  `tests/test_diff.py`(可脱离 KiCad 直接运行)
- 兼容两种板文件格式:KiCad ≤9 的 nm 整数坐标与 KiCad 10 的 mm 浮点坐标
- 图层图经 `kicad-cli pcb export svg --layers <层>` 导出后用 wx 光栅化
  (KiCad 10 的 `pcb render` 已改为 3D 渲染、不再支持按层输出)
- 两版图像通过**校准标记**实现板坐标 ↔ 像素的精确映射
  (向临时副本注入两个已知坐标的标记圆,再按像素质心求解仿射),
  保证红绿叠加像素级对齐
- 差异匹配策略:封装先按位号匹配(替换元件记录为「封装修改」),
  其余元素按 uuid 匹配

## 已知限制 · Known Limitations

- 大面积板子逐图层渲染需数秒,渲染在后台线程进行
- 板坐标超出 KiCad 内部 32 位 nm 范围(约 ±2147 mm)的元素
  与板框外元素无法渲染(由 KiCad/kicad-cli 决定)
- 两版板框尺寸差异较大时,红绿叠加以板坐标对齐,未变元素位置一致、
  但缩放有轻微差异(方案固有特性)
- 快照只记录 `.kicad_pcb`(原理图 `.kicad_sch` 不在范围内)

## 测试与开发 · Testing & Development

- 纯标准库单测(任意 Python 3.8+):`python tests/test_diff.py` 与
  `python tests/test_snapshot.py`
  *Pure-stdlib unit tests (any Python 3.8+)*
- 端到端(需 KiCad 10 自带 Python):先运行 `tests/make_sample_boards.py`
  生成样例板,再运行 `tests/e2e_render.py`(渲染管线)与
  `tests/e2e_ui.py`(两个窗口)
  *End-to-end (requires the Python bundled with KiCad 10): generate sample
  boards with `tests/make_sample_boards.py`, then run `tests/e2e_render.py`
  (render pipeline) and `tests/e2e_ui.py` (both windows).*

## 发布 · Release

### GitHub Releases

1. 打 tag 并推送:`git tag v1.1.0 && git push origin v1.1.0`
2. GitHub Actions 自动构建 PCM zip 并发布 Release。

### 提交 KiCad 官方插件仓库(可选)

官方要求见 <https://dev-docs.kicad.org/zh-cn/addons/>,本项目已满足:

- 打包结构:`plugins/` 平铺 + `resources/icon.png`(64x64)+ `metadata.json`;
- 元数据全英文;`identifier` 为 `com.github.miaomaioji.kicad-change-log`
  (逆序 DNS 命名);MIT 许可证与 GPL 兼容;
- 源码托管于 GitHub,满足 issue 跟踪要求。

步骤:

1. `python build_pcm.py` 生成 `dist/kicad_change_log_v1.1.0.zip` 与
   `dist/metadata.json`(含 `download_sha256` / `download_size` /
   `install_size`);
2. 确认 zip 已上传到 GitHub Release(CI 自动完成),
   保证 `download_url` 公开可访问;
3. 向 <https://gitlab.com/kicad/addons/metadata> 提交 MR:
   新建目录 `packages/com.github.miaomaioji.kicad-change-log/`,
   放入 `dist/metadata.json`。

*The package metadata is in English, uses the reverse-DNS identifier
`com.github.miaomaioji.kicad-change-log`, and is MIT licensed
(GPL-compatible), meeting the official repository requirements.*

## 许可 · License

[MIT](LICENSE)
