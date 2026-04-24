# RubikPi 3 — High-Level Audio Software Architecture 分析
# (圖片 + Yocto Metadata Layer 對應)

> 參考圖片：`Qualcomm_Linux_Audio/High-level audio software architecture.png`  
> 硬體平台：Qualcomm QCS6490 (SC7280) ＋ ES8316 Codec  
> Yocto layer：`meta-rubikpi-bsp` / `meta-rubikpi-distro`  
> 分析日期：2026-04-23（更新：2026-04-24）

---

## 一、架構圖總覽
![alt text](<../Qualcomm_Linux_Audio/High-level audio software architecture.png>)
圖源：https://docs.qualcomm.com/doc/80-70015-16/topic/features.html?product=895724676033554725&facet=Audio&version=1.2

架構圖由上至下分為五個層次：

圖例說明：
- **藍色 (Blue)** = Qualcomm 閉源 / 專有元件  
- **淺灰 (Light gray)** = 開源元件  
- **白色 (White)** = 硬體  
- **橙色雙箭頭** = 音頻資料流  
- **灰色雙箭頭** = 資料 + 控制  
- **黑色單箭頭** = 純控制訊號  

---

## 二、各 Layer 詳細分析

---

### Layer 1：Application Layer（應用層）

| 項目 | 說明 |
|------|------|
| 元件 | `Application`（使用者應用程式）|
| 顏色 | 白色（硬體/一般應用程式邊界）|
| 典型應用 | aplay/arecord、影音播放器、語音助手、GStreamer pipeline、Qt 音頻 App |

**角色：**  
使用者空間應用程式透過標準 POSIX API 或框架 API（如 PulseAudio Client API、GStreamer Element API）操作音頻。應用程式不直接接觸 ALSA / kernel，全由 Middleware 轉接。

---

### Layer 2：Middleware Layer（中介軟體層）

本層包含兩個主要元件，彼此通過雙向資料+控制通道連接：

#### 2-A：PulseAudio（Client Middleware — 淺灰色）

> **[官方說明](https://docs.qualcomm.com/doc/80-70015-16/topic/features.html?product=895724676033554725&facet=Audio&version=1.2)：** A sound server for POSIX OSes (mostly targeting Linux) that acts as a proxy and router between hardware device drivers and applications on single or multiple hosts.

> **📝 說明：** "Sound server" 是一個跑在 **user space** 的背景 daemon 程序（process），不在 Linux Kernel 內部。APP 透過 client library（`libpulse.so` / `libpipewire-0.3.so`）以 **Unix Domain Socket** 的方式與它通訊，而非直接 POSIX syscall。Sound server 再負責往下呼叫 PAL / ALSA kernel driver 存取硬體。

| 項目 | 說明 |
|------|------|
| 角色 | 通用音頻伺服器，處理多工程序混音、路由 |
| 接口 | 上層：PulseAudio Client API；下層：PAL / ALSA plugin |
| Yocto Recipe | `pulseaudio_17.0.bbappend`（meta-rubikpi-bsp） |
| Yocto Recipe | `pa-pal-plugins_1.0.bb`（meta-rubikpi-bsp） |
| 特殊配置 | 在 RubikPi3 中被設定為 **不自動啟動**（`Avoid PulseAudio service to start`），改以 PipeWire 取代 |

**Package Group 成員（`packagegroup-qcom-audio.bb` → `PULSEAUDIO_PKGS`）：**
```
pulseaudio-server
pulseaudio-module-loopback
pulseaudio-module-null-source
pulseaudio-module-combine-sink
pulseaudio-module-switch-on-port-available
pulseaudio-misc                            ← 補充（原文件缺漏）
pulseaudio-module-dbus-protocol           ← 補充（原文件缺漏）
pulseaudio-module-bluetooth-discover
pulseaudio-module-bluetooth-policy
pulseaudio-module-bluez5-discover
pulseaudio-module-bluez5-device
```

**`pulseaudio_17.0.bbappend` 補充說明：**
- 額外 patch：`0003-libpulse-Initialize-channel-map-for-7-8-channel-audio.patch`（7/8 聲道支援）、`0004-pulsecore-Update-desired-sample-spec-for-requested-c.patch`
- 安裝自訂 `system.pa` / `system_custom.pa`（包含 Bluetooth module 載入）
- `qcom-custom-bsp` 使用 `pulseaudio_custom.service`（服務不自動啟動，由 PipeWire 取代）
- `qcom-base-bsp` 使用標準 `pulseaudio.service`（一般 Qualcomm 平台仍啟動 PulseAudio）

> **RubikPi3 實際情況**：PulseAudio 已被 **PipeWire** 取代作為預設音頻伺服器。  
> 相關 Recipe：`qcom-pw-pal-plugin_git.bb`、`wireplumber_%.bbappend`

**`qcom-pw-pal-plugin_git.bb` 詳細說明：**

| 項目 | 說明 |
|------|------|
| 來源倉庫 | `pulseaudio-plugin.git`（`audio-algos.lnx.1.0.r1-rel`）—— 與 `pa-pal-plugins` 同源 |
| RubikPi3 Patch | `0001-modify-pipewire-configuration-for-rubikpi3.patch` |
| 部署 so | `libpipewire-module-pal.so` → `/usr/lib/pipewire-0.3/` |
| Systemd 服務 | `pipewire-pulse.service`、`pipewire-pulse.socket`、`98-qcom-pipewire.preset` |
| 設定檔 | `wireplumber.conf.d/60-disable-alsa.conf`（停用 ALSA backend）、`pipewire.conf.d/pw-pal-plugin.conf` |
| 依賴 | `qcom-agm`, `pipewire`, `qcom-pal`, `qcom-pal-headers` |

#### 2-B：GStreamer（MM Framework — 淺灰色）

| 項目 | 說明 |
|------|------|
| 角色 | 多媒體框架，處理影音流水線（pipeline）、編解碼 |
| 接口 | 上層：GStreamer API；下層：PulseAudio sink/src、ALSA plugin |
| Yocto Recipe | `gstreamer/`（meta-rubikpi-bsp 的 `recipes-multimedia/gstreamer/`） |
| 特殊修改 | `set zwp_linux_dmabuf_v1_interface to version 3`（顯示整合）|

---

### Layer 3：Hardware Abstraction Layer — HAL（硬體抽象層）

本層是 Qualcomm 音頻架構的核心，包含四個主要元件：

---

#### 3-A：PAL — Platform Abstraction Layer（藍色）

> **官方說明：** Provides higher-level audio-specific APIs to access the underlying audio hardware and drivers to enable feature rich audio use cases.

| 項目 | 說明 |
|------|------|
| 全稱 | Platform Abstraction Layer |
| 角色 | 統一音頻 HAL，對上層提供設備無關 API；對下層驅動 AGM、管理音頻會話 |
| 開源倉庫 | `git.codelinaro.org/clo/le/platform/vendor/qcom/opensource/arpal-lx.git` |
| 分支 | `audio-core.lnx.1.0.r1-rel` |
| Yocto Recipe | `qcom-pal_git.bb`（meta-rubikpi-bsp） |
| 依賴 | `tinyalsa`, `tinycompress`, `qcom-agm`, `qcom-kvh2xml`, `qcom-audioroute`, `fastrpc`, `qcom-pal-headers` |
| Systemd 服務 | `adsprpcd_audiopd.service`（管理 ADSP remote process daemon）|

**RubikPi3 專屬 Patch：**
```
0002-modifying-configuration-files.patch
0003-Modify-the-backend-used-by-the-speaker-mic.patch
0004-Enable-hdmi-to-add-a-new-device.patch
0005-Fixed-the-problem-of-audio-recording-failing-occasionally.patch
0006-Increase-the-default-volume-of-headphone-playback.patch
```

---

#### 3-B：ARGS — AudioReach Graph Service（藍色）

> **官方說明：** Consists of the Graph Service Layer (GSL), Generic Packet Router (GPR), and ACDB Management Layer (AML) modules. Handles initialization and creation of graphs as well as creation of packets for sending series of commands to SPF.

| 項目 | 說明 |
|------|------|
| 全稱 | AudioReach Graph Service（包含 GSL、GPR、AML 三個子模組）|
| 角色 | 管理音頻路由圖（Graph），橋接 PAL 與 SPF（DSP firmware）之間的 IPC 通道 |
| 開源倉庫 | `git.codelinaro.org/clo/le/platform/vendor/qcom-opensource/args.git` |
| 分支 | `audio-core.lnx.1.0.r1-rel` |
| Yocto Recipe | `qcom-args_git.bb`（meta-rubikpi-bsp） |
| 依賴 | `glib-2.0`, `diag`, `diag-router`, `linux-kernel-qcom-headers` |
| 推薦 Kernel 模組 | `kernel-module-audio-pkt`, `kernel-module-spf-core` |

**ACDB 整合：**  
ARGS 透過 ACDB（Audio Calibration Database）讀取校準資料，QACT（Qualcomm Audio Calibration Tool）可透過 USB 從 PC 端寫入 ACDB，實現即時調音。

---

#### 3-C：AGM — Audio Graph Manager（藍色）

> **官方說明：** Provides interfaces to allow TinyALSA-based mixer controls and PCM/compressed plug-ins to interact and enable various audio use cases.

| 項目 | 說明 |
|------|------|
| 全稱 | Audio Graph Manager |
| 角色 | 管理 ALSA PCM/Mixer 到 SPF Graph 的映射，提供 libalsa plugin 介面 |
| 開源倉庫 | `git.codelinaro.org/clo/le/platform/vendor/qcom/opensource/agm.git` |
| 分支 | `audio-core.lnx.1.0.r1-rel` |
| Yocto Recipe | `qcom-agm_git.bb`（meta-rubikpi-bsp）|
| 子目錄 | `agm/`（含 backend XML patch）|

**RubikPi3 專屬 Patch：**
```
0002_Modify_the_backend_conf_xml_file.patch
0003_Change_the_capture_format_of_ES8316_from_1ch_to_2ch.patch
0004_Change_the_HDMI_OUT_AUDIO_format_from_16_to_32bit.patch
0005_Enable_the_third_i2s.patch
0006_Enable_BTHS_record.patch
```

---

#### 3-D：TinyALSA（淺灰色）

| 項目 | 說明 |
|------|------|
| 角色 | 輕量 ALSA 使用者空間函式庫，提供 PCM/Mixer 基本 API |
| 用途 | AGM 底層 ALSA 操作、aplay/arecord 工具 |
| Yocto Recipe | `tinyalsa_1.1.1.qcom.bb`（meta-rubikpi-bsp）|
| 相關 | `tinycompress_1.2.11.qcom.bb`（壓縮音頻格式支援）|

---

#### ACDB — Audio Calibration Database（輔助元件）

> **官方說明：** Contains information about various audio use cases such as use case graphs, module calibration data, etc. The APPS processor parses ACDB files to retrieve the use case graph information used by SPF to instantiate the use case.

| 項目 | 說明 |
|------|------|
| 角色 | 儲存 SPF / Codec 音頻校準參數（EQ、增益、降噪等）|
| 工具 | QACT（PC 端 USB 連線調音）|
| Yocto Recipe | `qcom-acdbdata_git.bb`（包含 RubikPi3 專屬 ACDB 資料）|
| 部署路徑 | `/lib/firmware/qcom/qcs6490/`（對應 `qcom-audio-firmware_git.bb`）|

---

### Layer 4：Kernel Space（核心空間）

#### ASOC — ALSA System on Chip（淺灰色）

| 項目 | 說明 |
|------|------|
| 全稱 | ALSA System on Chip |
| 角色 | Linux 核心音頻子系統，提供 PCM/Mixer/DAPM 抽象；整合 Machine / Platform / Codec driver |
| Machine Driver | `sound/soc/qcom/qcm6490.c`（ASoC machine driver）|
| Codec Driver | `sound/soc/codecs/es8316.c`（ES8316 codec）|
| Platform Driver | q6apm / q6afe（Qualcomm APM/AFE kernel drivers）|
| Device Tree | `qcs6490-thundercomm-rubikpi3.dtsi`（I2C、MI2S、GPIO 定義）|
| Yocto Recipe | `recipes-kernel/`（`qcom-agm_git.bb` RRECOMMENDS `kernel-module-spf-core`）|

**ASOC 三層架構：**
```
Machine Driver (qcm6490.c)
    ├── Platform Driver (q6apm/q6afe)  ← 連接 SPF DSP
    └── Codec Driver (es8316.c)        ← 連接 ES8316 硬體
```

---

### Layer 5：LPAI — Low Power Audio Instruction（DSP 層）

#### SPF — Signal Processing Framework（藍色）

> **官方說明：** Modular framework that runs on the LPAI DSP. It provides the means to set up, configure, and execute signal processing modules for audio use cases.

| 項目 | 說明 |
|------|------|
| 全稱 | Signal Processing Framework（運行於 Qualcomm ADSP Q6 DSP）|
| 角色 | 在低功耗 DSP 上執行所有音頻信號處理：混音、EQ、降噪、回聲消除等 |
| 通訊方式 | 透過 `audio-pkt` kernel driver 與 host 側 ARGS 通訊 |
| 韌體路徑 | `/lib/firmware/qcom/qcs6490/`（由 `qcom-audio-firmware_git.bb` 打包）|
| Topology 檔案 | `qcs6490-rb3gen2-snd-card-tplg.conf`（音頻圖拓樸定義）|

#### Codec（白色 — 硬體）

| 項目 | 說明 |
|------|------|
| 硬體 | Everest Semiconductor ES8316 |
| 接口 | I2C（0x11，控制），I2S PRIMARY MI2S（音頻資料）|
| MCLK | LPASS MCLK1，24.576 MHz（永久開啟避免 POP 聲）|
| 功能 | DAC（耳機輸出）、ADC（MIC 輸入）、Jack 偵測（GPIO63）|

---

## 三、Yocto Layer 對應總表

### meta-rubikpi-bsp：`recipes-multimedia/audio/` 完整清單

> **Note：** `packagegroup-qcom-audio.bb` 依平台分兩組依賴：
> - `RDEPENDS:append:qcom-base-bsp`：基礎套件（firmware + PipeWire + PulseAudio modules）
> - `RDEPENDS:append:qcom-custom-bsp`：完整 HAL stack（HAL + Voice/SVA + DAC/Mercury 等）

#### HAL / Kernel 層

| Yocto Recipe | 對應架構元件 | 說明 |
|---|---|---|
| `qcom-pal_git.bb` | PAL（HAL） | Platform Abstraction Layer，含 RubikPi3 patch |
| `qcom-args_git.bb` | ARGS（HAL） | AudioReach Graph Service（GSL + GPR + AML）|
| `qcom-agm_git.bb` | AGM（HAL） | Audio Graph Manager，含 ES8316/HDMI patch |
| `tinyalsa_1.1.1.qcom.bb` | TinyALSA（HAL） | ALSA 使用者空間輕量函式庫 |
| `tinycompress_1.2.11.qcom.bb` | TinyALSA（HAL） | 壓縮音頻支援 |
| `qcom-pal-headers_git.bb` | PAL（HAL）| PAL API header |
| `qcom-audio-plugin-headers_git.bb` | PAL/AGM | Plugin headers |
| `qcom-capiv2-headers_git.bb` | HAL headers | CAPI v2（Common Audio Processor Interface v2）headers |
| `qcom-kvh2xml_git.bb` | HAL 配置 | Key-Value to XML 工具（給 PAL 用）|
| `qcom-audioroute_git.bb` | HAL 路由 | 音頻路由配置工具 |
| `qcom-acdbdata_git.bb` | ACDB | RubikPi3 音頻校準資料 |

#### SPF Firmware / Topology

| Yocto Recipe | 對應架構元件 | 說明 |
|---|---|---|
| `qcom-audio-firmware_git.bb` | SPF（LPAI） | Topology `.conf` + firmware；含 `qcm6490/`、`qcs6490/`、`sa8775p/` 各平台子目錄 |

#### Middleware（PulseAudio / PipeWire）

| Yocto Recipe | 對應架構元件 | 說明 |
|---|---|---|
| `pulseaudio_17.0.bbappend` | PulseAudio | 自訂 `system.pa`、多聲道 patch；custom-bsp 停用自動啟動 |
| `pa-pal-plugins_1.0.bb` | PulseAudio | PA → PAL 橋接 plugin |
| `qcom-pw-pal-plugin_git.bb` | PipeWire | PipeWire → PAL 橋接 plugin（RubikPi3 主力），含 RubikPi3 專屬 patch |
| `wireplumber_%.bbappend` | PipeWire | 啟用 BlueZ plugin |
| `qcom-pa-bt-audio_1.1.bb` | Bluetooth Audio | PA 藍牙音頻支援 |

#### Voice / SVA（聲音語音架構）

| Yocto Recipe | 對應架構元件 | 說明 |
|---|---|---|
| `qcom-sva-eai_2.0.bb` | SVA | Sound Voice Architecture — Engine Abstraction Interface（Qualcomm 專有預建）|
| `qcom-vui-interface-header_git.bb` | VUI | Voice UI Interface header |
| `qcom-vui-interface_git.bb` | VUI | Voice UI Interface plugin（來自 arpal-lx，DEPENDS: qcom-pal-headers, qcom-args）|
| `qcom-audio-systems_git.bb` | Audio Systems | 語音系統整合（DEPENDS: qcom-sva-eai, qcom-capiv2-headers；Qualcomm 專有預建）|
| `qcom-audiolisten_git.bb` | Audio Listen | Audio Listen headers（Qualcomm 專有預建）|
| `qcom-pa-pal-voiceui_git.bb` | PulseAudio VUI | Voice UI PulseAudio plugin |
| `qcom-pa-pal-acd_git.bb` | ACD | Audio Context Detection test app（DEPENDS: qcom-pal, qcom-vui-interface-header）|

#### DAC / Mercury（進階音頻處理）

| Yocto Recipe | 對應架構元件 | 說明 |
|---|---|---|
| `qcom-audio-expander_git.bb` | DAC/Expander | Audio Expander（Qualcomm 專有預建）|
| `qcom-audio-dac_git.bb` | DAC | Audio DAC processing（DEPENDS: qcom-audio-expander；Qualcomm 專有預建）|
| `qcom-dac-plugin_git.bb` | DAC plugin | DAC processing plugin |
| `qcom-dac-mer-testapp_git.bb` | DAC test | DAC Merge test application |
| `qcom-audio-mercury_git.bb` | Mercury | Audio Mercury（Qualcomm 專有預建）|
| `qcom-mercury-plugin_git.bb` | Mercury plugin | Mercury audio plugin |
| `qcom-mercuryflasher_git.bb` | Mercury | Mercury firmware flasher |

#### 系統工具 / 其他

| Yocto Recipe | 對應架構元件 | 說明 |
|---|---|---|
| `alsa-utils_%.bbappend` | ALSA 工具 | aplay/arecord 等工具 |
| `alsa-state.bbappend` | ALSA 狀態 | 移除 `/var/lib/alsa/asound.state`（避免靜態 mixer 快取干擾）|
| `qcom-audio-node_git.bb` | udev 規則 | 部署 `audio-node.rules` 至 udev（音頻裝置節點權限）|
| `qcom-audio-ftm_git.bb` | Factory Test | 音頻工廠測試工具 |
| `notify.bb` | 通知聲 | RubikPi3 系統音效 |
| `packagegroups/packagegroup-qcom-audio.bb` | 全層打包 | 定義 `PIPEWIRE_PKGS` / `PULSEAUDIO_PKGS`，分 base-bsp / custom-bsp |

### meta-rubikpi-distro：Image 定義

| 項目 | 說明 |
|------|------|
| `qcom-multimedia-image` | 包含完整 audio stack 的標準映像 |
| `DISTRO = "qcom-wayland"` | 預設 distro 配置 |
| 最新 Release | `v5.0.9-fc4`（2025-11-13）|

#### packagegroup-qcom-audio：PIPEWIRE_PKGS 清單

```
alsa-utils-alsactl
alsa-utils-amixer
${VIRTUAL-RUNTIME_alsa-state}
alsa-utils-alsaucm
alsa-utils-aplay
pipewire
pipewire-pulse
pipewire-alsa
wireplumber
libpipewire
pipewire-modules-meta
pipewire-tools
pipewire-spa-tools
```

---

## 四、元件相依關係圖（Dependency Graph）

```
Application
    │
    ▼
PulseAudio / PipeWire (Middleware)
    │  pa-pal-plugins / qcom-pw-pal-plugin
    │    └─ qcom-pw-pal-plugin: libpipewire-module-pal.so → /usr/lib/pipewire-0.3/
    ▼
PAL (qcom-pal_git.bb)
    │  DEPENDS: tinyalsa, tinycompress, qcom-agm, qcom-kvh2xml, qcom-audioroute, fastrpc
    ├──► AGM (qcom-agm_git.bb)
    │        │  使用 ALSA PCM/Mixer kernel interface
    │        ▼
    │    ASOC kernel (qcm6490.c machine driver)
    │        ├── ES8316 Codec driver (es8316.c)
    │        └── q6apm/q6afe Platform driver
    │
    ├──► ARGS (qcom-args_git.bb)
    │        │  DEPENDS: glib-2.0, diag, linux-kernel-qcom-headers
    │        │  RRECOMMENDS: kernel-module-audio-pkt, kernel-module-spf-core
    │        │  讀取 ACDB (qcom-acdbdata_git.bb)
    │        ▼
    │    SPF (ADSP Q6 firmware)
    │        │  Topology: qcs6490-rb3gen2-snd-card-tplg.conf
    │        └──► Codec 硬體 (ES8316 via I2S)
    │
    └──► VUI / SVA (qcom-vui-interface_git.bb)
             │  DEPENDS: qcom-pal-headers, qcom-kvh2xml, qcom-vui-interface-header, qcom-args
             ├── qcom-audio-systems (DEPENDS: qcom-sva-eai, qcom-capiv2-headers)
             └── qcom-pa-pal-acd  (Audio Context Detection)
```

---

## 五、音頻信號流路徑（對應架構圖資料流）

### Playback（播放）

```
Application
  │ PulseAudio/PipeWire API
  ▼
PulseAudio Server / PipeWire
  │ pa-pal-plugin / pw-pal-plugin
  ▼
PAL API (libpal.so)
  │
  ├── ARGS → SPF (ADSP) → [DSP 混音/EQ 處理]
  │
  └── AGM → ASOC (q6apm) → MI2S PRIMARY_RX
         → GPIO97(BCLK)/GPIO100(WS)/GPIO98(DATA0)
         → ES8316 DAC
         → 耳機輸出 (Headphone Jack)
```

### Capture（錄音）

```
麥克風 (MIC)
  → ES8316 ADC
  → GPIO99(DATA1) / I2S MI2S PRIMARY_TX
  → ASOC (q6apm)
  → AGM
  → PAL API
  → PulseAudio/PipeWire
  → Application
```

### QACT 校準流

```
PC (QACT 工具)
  → USB
  → ACDB (qcom-acdbdata) [/lib/firmware/qcom/qcs6490/]
  → ARGS 讀取
  → SPF 套用校準參數
```

---

## 六、RubikPi3 特殊設計要點

| 設計點 | 說明 |
|--------|------|
| MCLK 永久開啟 | ES8316 需持續 24.576 MHz MCLK（qcm6490.c：`pri_mi2s_mclk_count` 只增不減）|
| PipeWire 取代 PulseAudio | PulseAudio 僅保留 module 套件，服務由 WirePlumber + PipeWire 取代 |
| ES8316 init-regs | DT 中 40+ 寄存器初始化序列，確保啟動時正確配置 Codec |
| AGM 2ch Capture | Patch `0003_Change_the_capture_format_of_ES8316_from_1ch_to_2ch.patch` 修正錄音聲道 |
| HDMI 音頻 | QUATERNARY_MI2S_RX → LT9611 HDMI bridge，格式改為 32bit（AGM patch）|
| GPIO117 電源控制 | `regulator-fixed` + `regulator-always-on`，ES8316 永久供電 |
| Jack 偵測反轉 | `everest,jack-detect-inverted = <1>`（RubikPi3 硬體設計差異）|
| PipeWire 停用 ALSA backend | `60-disable-alsa.conf`（wireplumber）確保 PipeWire 不直接操作 ALSA，全走 PAL |
| packagegroup 雙路分支 | `qcom-base-bsp` 僅含基本套件；`qcom-custom-bsp` 含完整 HAL + Voice/DAC/Mercury |

---

## 七、進階元件補充說明

### SVA — Sound Voice Architecture（語音偵測）

SVA 是 Qualcomm 提供的語音辨識架構，運行於 ADSP DSP 上，負責低功耗喚醒詞偵測（Always-On）：

| 元件 | Recipe | 說明 |
|------|--------|------|
| SVA EAI | `qcom-sva-eai_2.0.bb` | Engine Abstraction Interface（閉源預建）|
| VUI Interface | `qcom-vui-interface_git.bb` | Voice UI plugin，橋接 PAL 與 SVA（arpal-lx 開源）|
| VUI Headers | `qcom-vui-interface-header_git.bb` | VUI API header |
| Audio Systems | `qcom-audio-systems_git.bb` | 整合 SVA + CAPI v2 的系統層（閉源預建）|
| CAPI v2 Headers | `qcom-capiv2-headers_git.bb` | Common Audio Processor Interface v2 headers |
| Audio Listen | `qcom-audiolisten_git.bb` | Listen headers（閉源預建）|
| ACD | `qcom-pa-pal-acd_git.bb` | Audio Context Detection 測試 app |
| VoiceUI PA Plugin | `qcom-pa-pal-voiceui_git.bb` | VUI PulseAudio plugin |

### Mercury / DAC（音頻擴展處理）

Mercury 和 DAC 系列是 Qualcomm 提供的進階音頻信號處理元件（如高保真 DAC、音頻擴展器），通常為閉源預建：

| 元件 | Recipe | 說明 |
|------|--------|------|
| Audio Expander | `qcom-audio-expander_git.bb` | 音頻擴展器（閉源預建）|
| Audio DAC | `qcom-audio-dac_git.bb` | DAC 處理函式庫（DEPENDS: qcom-audio-expander）|
| DAC Plugin | `qcom-dac-plugin_git.bb` | DAC pipeline plugin |
| DAC Merge Test | `qcom-dac-mer-testapp_git.bb` | DAC 合併測試工具 |
| Audio Mercury | `qcom-audio-mercury_git.bb` | Mercury 處理函式庫（閉源預建）|
| Mercury Plugin | `qcom-mercury-plugin_git.bb` | Mercury pipeline plugin |
| Mercury Flasher | `qcom-mercuryflasher_git.bb` | Mercury firmware 燒錄工具 |

> **備註**：RubikPi3 基本音頻功能（耳機播放 / MIC 錄音 / HDMI）不依賴 Mercury/DAC 元件；  
> 這些元件由 `qcom-custom-bsp` packagegroup 引入，為選配的進階功能。

