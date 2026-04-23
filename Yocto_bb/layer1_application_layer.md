# Layer 1：Application Layer — 深入分析
# User-Space 音頻使用方式 ＆ Yocto Metadata Layer 對應

> 上層文件：[audio_stack_yocto_analysis.md](audio_stack_yocto_analysis.md)  
> 硬體平台：Qualcomm QCS6490 (SC7280) ＋ ES8316 Codec  
> 分析日期：2026-04-23

---

## 一、Application Layer 在架構中的位置

```
┌────────────────────────────────────────────────────────┐
│  ★ Application Layer  (本文件聚焦層)                    │
│    aplay / arecord / GStreamer App / Qt App / 自製 App  │
└──────────────────┬─────────────────────────────────────┘
                   │  PulseAudio Client API / PipeWire API
                   │  GStreamer Element API
                   ▼
┌────────────────────────────────────────────────────────┐
│  Middleware Layer  (PulseAudio / PipeWire / GStreamer)  │
└────────────────────────────────────────────────────────┘
```

Application Layer 的應用程式<span style="color:red">**不直接操作 ALSA kernel driver 或 PAL**</span>，  
而是透過中間層（PipeWire / PulseAudio / GStreamer）存取音頻硬體。  
這種設計確保多個程序可同時使用音頻，並統一由 Middleware 管理路由與混音。

---

## 二、User-Space 音頻 API 路徑

RubikPi 3 上的 User-Space 應用程式有以下四條 API 路徑可選：

---

### 路徑 A：PipeWire Native API（推薦，RubikPi3 主力）

```
App
 │  #include <pipewire/pipewire.h>
 │  pw_init() / pw_stream_new() / pw_stream_connect()
 ▼
libpipewire-0.3.so          ← Yocto: pipewire (meta-openembedded/meta-multimedia)
 │
 ▼
PipeWire daemon (pipewire)  ← Yocto: pipewire
WirePlumber (session manager) ← Yocto: wireplumber_%.bbappend (meta-rubikpi-bsp)
 │
 ▼
qcom-pw-pal-plugin          ← Yocto: qcom-pw-pal-plugin_git.bb (meta-rubikpi-bsp)
 │
 ▼
PAL → AGM → ASOC → ES8316
```

**特色：**
- 低延遲、支援多媒體混音
- `pipewire-pulse`：提供 PulseAudio 相容 socket，舊版 PA 應用程式無需修改即可使用
- `pipewire-alsa`：ALSA PCM plugin，舊版 ALSA 應用程式（如 `aplay`）也透過 PipeWire 路由
- WirePlumber 負責節點（node）策略管理：哪個 App 接哪個硬體裝置

---

### 路徑 B：PulseAudio Client API（相容路徑）

```
App
 │  #include <pulse/pulseaudio.h>
 │  pa_simple_write() / pa_mainloop_*()
 ▼
libpulse.so                 ← 實際由 pipewire-pulse 實作（PulseAudio 相容層）
 │
 ▼
PipeWire daemon (透過 pipewire-pulse socket)
 │
 ▼
qcom-pw-pal-plugin → PAL → AGM → ASOC → ES8316
```

> **注意：** RubikPi3 上 `pulseaudio-server` 雖已安裝但**不自動啟動**。  
> 應用程式呼叫 `libpulse.so` 時，實際連接到的是 `pipewire-pulse` 提供的相容 socket。

---

### 路徑 C：ALSA 命令列工具（低階直接存取）

```
aplay / arecord / amixer / alsactl
 │  使用 libasound.so + pipewire-alsa ALSA PCM plugin
 ▼
PipeWire daemon
 │
 ▼
qcom-pw-pal-plugin → PAL → AGM → ASOC → ES8316
```

**常用指令（RubikPi3 上實測）：**

```bash
# 列出音頻裝置
aplay -l

# 播放 wav 檔
aplay -D default test.wav

# 錄音 5 秒
arecord -D default -d 5 -f S16_LE -r 48000 -c 2 rec.wav

# 查看 mixer 控制
amixer -c 0 contents

# 儲存/還原 ALSA 狀態
alsactl store
alsactl restore
```

**注意：** `aplay` 的 `-D default` 實際透過 `pipewire-alsa` plugin 路由到 PipeWire，  
不直接走 ALSA kernel interface。

---

### 路徑 D：GStreamer Pipeline（多媒體應用）

```
App / gst-launch-1.0
 │  gst_element_factory_make("pulsesrc"/"pipewiresrc"/"alsasrc", ...)
 │  gst_element_factory_make("pulsesink"/"pipewiresink"/"alsasink", ...)
 ▼
libgstreamer-1.0.so + gstreamer1.0-plugins-good/bad
 │  PulseAudio sink/src element 或 PipeWire sink/src element
 ▼
PipeWire daemon
 │
 ▼
qcom-pw-pal-plugin → PAL → AGM → ASOC → ES8316
```

**常用 Pipeline 範例：**

```bash
# 播放音頻檔案
gst-launch-1.0 filesrc location=test.wav ! wavparse ! audioconvert ! pulsesink

# 錄音到檔案
gst-launch-1.0 pulsesrc ! audioconvert ! wavenc ! filesink location=rec.wav

# 即時麥克風 → 喇叭（loopback 測試）
gst-launch-1.0 pulsesrc ! pulsesink

# HDMI 音頻輸出
gst-launch-1.0 filesrc location=test.mp4 ! qtdemux ! aacparse ! avdec_aac \
  ! audioconvert ! pulsesink device=alsa_output.platform-soc_sound.hdmi-stereo
```

---

## 三、Audio FTM — 工廠測試應用程式

| 項目 | 說明 |
|------|------|
| 全名 | Audio Factory Test Mode |
| 用途 | 生產線音頻功能驗證：喇叭、麥克風、耳機 |
| 開源倉庫 | `git.codelinaro.org/clo/le/platform/vendor/qcom-opensource/audio_ftm.git` |
| Yocto Recipe | `qcom-audio-ftm_git.bb`（meta-rubikpi-bsp）|
| 依賴 | `tinyalsa`, `glib-2.0`, `qcom-agm`, `qcom-kvh2xml`, `qcom-args` |
| 設定檔路徑 | `/etc/`（`qcm6490/` 子目錄，do_install:append:qcm6490）|

FTM 工具**直接呼叫 AGM / TinyALSA API**，繞過 PipeWire/PulseAudio，適用於工廠環境的快速測試。

---

## 四、Yocto Metadata Layer 對應分析

Application Layer 的軟體套件由以下 **四個 Layer 層層組合**：

### 4-1：`poky/meta`（OE Core）

提供最基礎的音頻工具鏈：

| Recipe | 套件 | 說明 |
|--------|------|------|
| `alsa-lib` | `libasound.so` | ALSA 使用者空間函式庫（所有 ALSA 應用程式基礎）|
| `alsa-utils` | `aplay`, `arecord`, `amixer`, `alsactl` | 命令列音頻工具 |

### 4-2：`meta-openembedded/meta-multimedia`（OE MM Layer）

提供 PulseAudio、PipeWire、GStreamer 核心：

| Recipe | 套件 | 說明 |
|--------|------|------|
| `pulseaudio` | `libpulse`, `pulseaudio-server` | PulseAudio 聲音伺服器 |
| `pipewire` | `pipewire`, `pipewire-pulse`, `pipewire-alsa`, `libpipewire` | PipeWire 多媒體伺服器 |
| `wireplumber` | `wireplumber` | PipeWire session manager |
| `gstreamer1.0` | `libgstreamer-1.0.so` | GStreamer 框架核心 |
| `gstreamer1.0-plugins-base` | 基礎 GStreamer plugins | audioconvert, audioresample 等 |
| `gstreamer1.0-plugins-good` | 良好品質 GStreamer plugins | wavparse, pulsesrc/sink 等 |
| `gstreamer1.0-plugins-bad` | 實驗性 GStreamer plugins | pipewiresrc/sink 等 |

### 4-3：`meta-rubikpi-bsp`（BSP Layer — RubikPi 客製化）

BSP Layer 透過 `.bbappend` 和新 Recipe 客製化上游套件：

| Recipe | 作用 | 說明 |
|--------|------|------|
| `pulseaudio_17.0.bbappend` | 停用 PA 自動啟動 | `Avoid PulseAudio service to start`，讓 PipeWire 接管 |
| `alsa-utils_%.bbappend` | 新增 qcom override | `do_install:append:qcom` 確保 alsactl 正確安裝 |
| `alsa-state.bbappend` | 移除 `/var/lib/alsa/asound.state` | 避免 ALSA state 衝突 |
| `gstreamer1.0-plugins-bad_1.22%.bbappend` | 修正 Wayland dmabuf 版本 | `zwp_linux_dmabuf_v1_interface` → version 3（影像/音頻同步）|
| `qcom-pw-pal-plugin_git.bb` | PipeWire → PAL 橋接 | **關鍵**：PipeWire 與 Qualcomm HAL 的橋接 plugin（RubikPi3 主力路徑）|
| `wireplumber_%.bbappend` | 啟用 BlueZ | 支援藍牙音頻 A2DP/HFP |
| `pa-pal-plugins_1.0.bb` | PulseAudio → PAL 橋接 | PA 與 Qualcomm HAL 的橋接 plugin（備用路徑）|
| `qcom-audio-node_git.bb` | udev rules | `/lib/udev/rules.d/audio-node.rules`（設備節點建立規則）|
| `notify.bb` | 系統通知音效 | RubikPi3 系統事件音效（開機聲、提示音）|
| `packagegroup-qcom-audio.bb` | 音頻套件組 | 定義 `PIPEWIRE_PKGS` 和 `PULSEAUDIO_PKGS`，由 distro layer 引用 |

**`packagegroup-qcom-audio.bb` PIPEWIRE_PKGS 完整清單：**
```bitbake
PIPEWIRE_PKGS = " \
    alsa-utils-alsactl \
    alsa-utils-amixer \
    ${VIRTUAL-RUNTIME_alsa-state} \
    alsa-utils-alsaucm \
    alsa-utils-aplay \
    pipewire \
    pipewire-pulse \
    pipewire-alsa \
    wireplumber \
    libpipewire \
    pipewire-modules-meta \
    pipewire-tools \
    pipewire-spa-tools \
"
```

**`qcom-custom-bsp` 追加的應用程式套件：**
```bitbake
# RDEPENDS:${PN}:append:qcom-custom-bsp
tinyalsa         # 低階 ALSA 工具
qcom-agm         # AGM 工具（aplay-agm 等）
qcom-audio-ftm   # 工廠測試工具
qcom-audioroute  # 音頻路由設定工具
qcom-audio-systems  # 系統音頻設定
qcom-sva-eai     # 語音活動偵測
qcom-pw-pal-plugin  # PipeWire PAL plugin
notify           # 系統音效
```

### 4-4：`meta-rubikpi-distro`（Distro Layer — 映像組裝）

Distro Layer 定義哪些套件組進入最終映像：

| Recipe | 作用 |
|--------|------|
| `packagegroup-qcom-multimedia.bb` | 聚合所有多媒體套件：包含 GStreamer + `packagegroup-qcom-audio` |
| `qcom-multimedia-image.bb` | 最終映像 recipe：引入 `packagegroup-qcom-multimedia` + `packagegroup-rubikpi` |
| `DISTRO = "qcom-wayland"` | 指定 Wayland 顯示後端（配合 Weston）|

**套件引用鏈：**
```
qcom-multimedia-image.bb                  [meta-rubikpi-distro]
  └── packagegroup-qcom-multimedia         [meta-rubikpi-distro]
        └── packagegroup-qcom-audio        [meta-rubikpi-bsp]
              ├── PIPEWIRE_PKGS            [meta-openembedded]
              │     ├── pipewire
              │     ├── pipewire-pulse
              │     ├── wireplumber
              │     └── alsa-utils-*      [poky/meta]
              └── (qcom-custom-bsp)
                    ├── qcom-pw-pal-plugin [meta-rubikpi-bsp]
                    ├── qcom-audio-ftm     [meta-rubikpi-bsp]
                    └── notify             [meta-rubikpi-bsp]
```

---

## 五、API 呼叫完整路徑對照表

| 應用程式類型 | API / Library | 中間層 | PAL 接口 | Yocto 來源 Layer |
|---|---|---|---|---|
| PipeWire 原生 App | `libpipewire-0.3.so` | PipeWire daemon | `qcom-pw-pal-plugin` | meta-openembedded |
| PulseAudio 相容 App | `libpulse.so` | pipewire-pulse | `qcom-pw-pal-plugin` | meta-openembedded + meta-rubikpi-bsp |
| ALSA App（aplay 等）| `libasound.so` | pipewire-alsa plugin | `qcom-pw-pal-plugin` | poky/meta + meta-rubikpi-bsp |
| GStreamer App | `libgstreamer-1.0.so` | pulsesink / pipewiresink | `qcom-pw-pal-plugin` | meta-openembedded |
| 工廠測試（FTM）| TinyALSA / AGM API 直接呼叫 | 無（直接到 AGM）| — | meta-rubikpi-bsp |

---

## 六、PipeWire 設定客製化（RubikPi3 專屬）

RubikPi3 對 PipeWire 進行了客製化設定（`audio: pipewire: modify pipewire configuration for rubikpi3`）：

- **`qcom-pw-pal-plugin`** 作為 PipeWire 的 PAL sink/source node，  
  替代標準 ALSA plugin，讓 PipeWire 能夠透過 PAL 存取 Qualcomm ADSP 音頻路徑。
- WirePlumber 設定確保 `qcom-pw-pal-plugin` 的節點優先度高於普通 ALSA 節點。
- `pipewire-pulse` 提供 `/run/user/0/pulse/native` socket，  
  舊版 PulseAudio 應用程式（包含 Qt multimedia 等）自動發現並連接。

```
/etc/pipewire/pipewire.conf.d/   ← PipeWire 主設定
/etc/wireplumber/               ← WirePlumber 路由策略
/usr/lib/pipewire-0.3/          ← PipeWire 模組（含 qcom-pw-pal-plugin）
```

---

## 七、音頻設備節點（udev rules）

`qcom-audio-node_git.bb` 安裝的 udev rules（`/lib/udev/rules.d/audio-node.rules`）負責：

1. 當 ALSA PCM 設備出現時，建立 `/dev/snd/pcmC0D0p`（播放）、`/dev/snd/pcmC0D0c`（錄音）節點
2. 設定正確的 group permission（`audio` group）
3. 確保 PipeWire 和 ALSA 應用程式都能正常存取設備節點

---

## 八、Bluetooth 音頻應用路徑

RubikPi3 支援藍牙音頻（A2DP / HFP）：

```
藍牙耳機
  │ A2DP / HFP profile
  ▼
BlueZ daemon                       ← meta-openembedded/meta-networking
  │ BlueZ D-Bus API
  ▼
WirePlumber (bluez plugin)         ← wireplumber_%.bbappend (meta-rubikpi-bsp)
  │ 建立藍牙 Audio Node
  ▼
PipeWire daemon
  │
  ▼
App (pipewire / pulseaudio API)
```

套件支援：
- `pulseaudio-module-bluetooth-discover`
- `pulseaudio-module-bluez5-discover`
- `pulseaudio-module-bluez5-device`
- WirePlumber bluez plugin（由 `wireplumber_%.bbappend` 啟用）

---

## 九、小結：Application Layer Yocto Layer 職責劃分

| Layer | 職責 | 音頻相關貢獻 |
|-------|------|-------------|
| `poky/meta` (OE Core) | 基礎工具鏈 | `alsa-lib`、`alsa-utils` |
| `meta-openembedded/meta-multimedia` | 多媒體中介軟體 | `pulseaudio`、`pipewire`、`wireplumber`、`gstreamer1.0*` |
| `meta-rubikpi-bsp` (BSP) | Qualcomm 平台客製化 | `qcom-pw-pal-plugin`、PA/alsa-utils bbappend、`qcom-audio-ftm`、`notify`、`packagegroup-qcom-audio` |
| `meta-rubikpi-distro` (Distro) | 映像組裝與設定 | `qcom-multimedia-image`、`packagegroup-qcom-multimedia` |
