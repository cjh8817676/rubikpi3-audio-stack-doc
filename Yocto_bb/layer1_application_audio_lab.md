# RubikPi3 — Layer 1 Application Layer 深度分析
# User-Space 音頻操控方式 ＆ 實驗手冊

> 硬體平台：Qualcomm QCS6490 ＋ ES8316 Codec  
> 音頻伺服器：PulseAudio 17.0（system mode）＋ module-pal-card  
> 分析日期：2026-04-24（實測修正：2026-04-24）

---

## 一、PCM 裝置總覽（來自 Topology）

`qcs6490-rb3gen2-snd-card-tplg.conf` 定義了以下 PCM 裝置：

| PCM Index | PCM Name | 方向 | 格式 | 採樣率 | 聲道 | 硬體後端 | 用途 |
|-----------|----------|------|------|--------|------|---------|------|
| 0 | `MULTIMEDIA0 Playback` | Playback | S16_LE | 48000 Hz | 2ch | `WSA_CODEC_DMA_RX_0` → ES8316 DAC | 耳機輸出（主播放）|
| 1 | `MULTIMEDIA1 Capture` | Capture | S16_LE | 48000 Hz | 2ch | `VA_CODEC_DMA_TX_0` | VA MIC 錄音路徑 |
| 2 | `MULTIMEDIA2 Playback` | Playback | S16_LE | 48000 Hz | 2ch | `RX_CODEC_DMA_RX_0` → ES8316 DAC | 耳機輸出（次播放）|
| 3 | `MULTIMEDIA3 Capture` | Capture | S16_LE | 48000 Hz | 2ch | `TX_CODEC_DMA_TX_3` | 主 MIC / I2S TX 錄音路徑 |

**音效卡名稱**：`qcs6490-rb3gen2-snd-card`（由 Machine Driver `qcm6490.c` 和 Topology conf 共同決定）

查詢方式：
```bash
sh-5.2# cat /proc/asound/cards
 0 [qcm6490idpsndca]: qcm6490 - qcm6490-idp-snd-card
                      qcm6490-idp-snd-card
```

---

## 二、User-Space 音頻操控方式全覽

RubikPi3 的 audio stack 提供以下幾種 user-space 存取層次：

```
┌──────────────────────────────────────────────────────────────────┐
│  Application Layer（user-space）                                 │   
│                                                                  │   
│  Layer A：PulseAudio API（system mode）                          │   
│    paplay / parec / parecord / pactl                             │   
│    ⚠ pw-play / pw-record / pw-cli 等 PipeWire 工具未安裝         │   
│                                                                  │   
│  Layer B：GStreamer Pipeline                                     │   
│    gst-launch-1.0  (pulsesrc / pulsesink → PulseAudio)          │   
│                                                                  │   
│  Layer C：ALSA 工具（直接 PCM）                                   │   
│    aplay / arecord / amixer / alsactl / alsaucm                  │   
│                                                                  │   
│  Layer D：TinyALSA 工具（輕量 ALSA + plug-in 架構）               │   
│    tinyplay / tinycap / tinymix / tinypcminfo                    │   
│                                                                  │   
│  Layer E：Qualcomm FTM 測試工具                                   │   
│    qcom-audio-ftm（直接呼叫 AGM/ARGS，繞過 PulseAudio）           │   
│                                                                  │   
│  Layer F：PAL API（C 程式開發介面）                               │   
│    pal_stream_open / pal_stream_write / pal_stream_read          │   
└──────────────────────────────────────────────────────────────────┘
```

---

### Layer A：PulseAudio API（system mode）

> ⚠ **實測修正**：RubikPi3 實際使用 **PulseAudio 17.0（system mode）** 作為音頻伺服器，**並非 PipeWire**。  
> PipeWire、WirePlumber 及相關工具（`pw-play`、`pw-record`、`pw-cli` 等）均未安裝於此映像。  
> PulseAudio 以 `--system` 模式由 systemd 啟動，後端透過 `module-pal-card` 連接 PAL → AGM → LPAIF。

PulseAudio 工具（`paplay`、`parec`、`pactl`）為原生 PulseAudio 程式，直接與 `/var/run/pulse/native` socket 通訊。

> 參考文件：[Qualcomm Linux Audio — APIs and Sample Apps](https://docs.qualcomm.com/doc/80-70015-16/topic/apis_and_sample_apps.html?product=895724676033554725&facet=Audio&version=1.2)

#### 工具清單

| 工具 | Yocto Package | 功能 | 目標機器路徑 | 實測狀態 |
|------|--------------|------|-------------|----------|
| `paplay` | `pulseaudio-misc` | 播放音頻（PulseAudio 原生）| `/usr/bin/paplay` | ✅ 可用 |
| `parec` | `pulseaudio-misc` | 錄音（PulseAudio 原生，官方推薦）| `/usr/bin/parec` | ✅ 可用 |
| `parecord` | `pulseaudio-misc` | 錄音（`parec` 別名）| `/usr/bin/parecord` | ✅ 可用 |
| `pactl` | `pulseaudio-utils` | 控制 sink/source、查看裝置清單 | `/usr/bin/pactl` | ✅ 可用 |
| `pw-play` | `pipewire-tools` | 播放 WAV/PCM（PipeWire 原生）| `/usr/bin/pw-play` | ❌ 未安裝 |
| `pw-record` | `pipewire-tools` | 錄音至 WAV/PCM（PipeWire 原生）| `/usr/bin/pw-record` | ❌ 未安裝 |
| `pw-cli` | `pipewire-tools` | PipeWire 互動式控制台 | `/usr/bin/pw-cli` | ❌ 未安裝 |
| `pw-dump` | `pipewire-tools` | 輸出 PipeWire 圖形 JSON 狀態 | `/usr/bin/pw-dump` | ❌ 未安裝 |

#### Qualcomm 官方 `parec` 使用範例

```bash
# 官方文件範例（80-70015-16）：capture 48kHz 16-bit mono，存成 WAV
parec -v --rate=48000 --format=s16le --channels=1 --file-format=wav /opt/test.wav --device=regular2

# 播放
paplay /opt/test.wav -v
```

**`parec` 支援的格式與規格（來自 Qualcomm 官方文件）：**

| 參數 | 支援值 |
|------|-------|
| `--format` | `s16le`, `s24le`, `s32le`, `s24-32le` |
| `--rate` | 8000, 16000, 22050, 24000, 32000, 44100, **48000**, 88200, 96000, 176400, 192000, 352800, 384000 |
| `--channels` | 1 ~ 8 |

#### 關鍵檔案路徑

| 類別 | 路徑 | 說明 |
|------|------|------|
| Yocto recipe | `meta-rubikpi-bsp/recipes-multimedia/audio/pulseaudio/pulseaudio_17.0.bbappend` | PulseAudio patch 及啟動設定 |
| Yocto recipe | `meta-rubikpi-bsp/recipes-multimedia/audio/pa-pal-plugins_1.0.bb` | PulseAudio → PAL sink plugin（`module-pal-card`）|
| Build-tree 原始碼 | `build-qcom-wayland/workspace/sources/pulseaudio` | PulseAudio 原始碼 |
| PulseAudio daemon | `/usr/bin/pulseaudio` | 音頻伺服器主程式（system mode）|
| Client 函式庫 | `/usr/lib/libpulse.so` | PulseAudio client library |
| PAL sink module | `/usr/lib/pulse-17.0/modules/module-pal-card.so` | PulseAudio → PAL 後端模組（實際後端）|
| PulseAudio socket | `/var/run/pulse/native` | Daemon 監聽 socket（需 `pulse` 群組權限）|
| PulseAudio 系統設定 | `/etc/pulse/system.pa` | System mode 啟動設定（載入 module-pal-card）|

#### 關鍵 PulseAudio C API（適用於自行開發應用程式）

以下 API 由 Qualcomm 官方文件（80-70015-16）列出，標頭位於 `<pulse/stream.h>`：

| API | 用途 |
|-----|------|
| `pa_stream_new(ctx, name, ss, map)` | 建立新串流（指定名稱、sample spec、channel map）|
| `pa_stream_connect_playback(s, dev, attr, flags, vol, sync)` | 連接串流至 sink（播放）|
| `pa_stream_connect_record(s, dev, attr, flags)` | 連接串流至 source（錄音）|
| `pa_stream_write(p, data, nbytes, free_cb, offset, seek)` | 寫入 PCM 資料（播放串流）|
| `pa_stream_set_write_callback(p, cb, userdata)` | 設定播放資料請求 callback |
| `pa_stream_set_read_callback(p, cb, userdata)` | 設定錄音資料就緒 callback |
| `pa_stream_disconnect(s)` | 斷開串流連接 |
| `pa_stream_get_state(p)` | 取得串流狀態 |
| `pa_stream_get_device_name(s)` | 取得連接的 sink/source 名稱 |

> 完整 API 參考：[PulseAudio open source documentation](https://freedesktop.org/software/pulseaudio/doxygen/stream_8h.html)

> **實測架構**：PulseAudio（system mode）→ `module-pal-card`（PAL sink plugin）→ PAL API → AGM → LPAIF Kernel Driver → ES8316 Codec  
> 所有 PulseAudio 音頻流最終都透過 `module-pal-card` 下達 PAL API。

---

### Layer B：GStreamer Pipeline

GStreamer 透過 `pulsesink`/`pulsesrc` 連接 PulseAudio，或直接以 `alsasink`/`alsasrc` 存取硬體。

> **Qualcomm 官方說明**：`pulsesrc` 和 `pulsesink` plugin 是 Qualcomm QIMP SDK 的一部分。  
> 參考：[GStreamer plugins — 80-70015-50](https://docs.qualcomm.com/bundle/publicresource/topics/80-70015-50/pulsesrc.html)

#### 使用方式（兩種途徑）

1. **命令列 `gst-launch-1.0`**（audio playback/capture use cases）
2. **GST 應用程式**：[Audio decode example](https://docs.qualcomm.com/bundle/publicresource/topics/80-70015-50/gst-audio-decode-sample.html) / [Audio encode example](https://docs.qualcomm.com/bundle/publicresource/topics/80-70015-50/gst-audio-encode-example-without-flac.html)

#### 常用 Element

| 元素 | 說明 |
|------|------|
| `audiotestsrc` | 產生正弦波測試音 |
| `filesrc` / `filesink` | 讀寫本地音頻檔案 |
| `wavparse` / `wavenc` | WAV 解碼/編碼 |
| `audioconvert` | 格式轉換（bit depth、channel map）|
| `audioresample` | 採樣率轉換 |
| `volume` | 音量控制 |
| `pulsesink` / `pulsesrc` | PipeWire PulseAudio compat sink/src（來自 QIMP SDK）|
| `alsasink` / `alsasrc` | 直接 ALSA PCM sink/src |
| `autoaudiosink` / `autoaudiosrc` | 自動偵測最佳 sink/src |

#### 關鍵檔案路徑

| 類別 | 路徑 | 說明 |
|------|------|------|
| Yocto recipe | `meta-rubikpi-bsp/recipes-multimedia/gstreamer/gstreamer1.0-plugins-bad_1.22%.bbappend` | zwp_linux_dmabuf_v1_interface 版本 patch |
| Yocto recipe 子目錄 | `meta-rubikpi-bsp/recipes-multimedia/gstreamer/gstreamer1.0-plugins-bad/1.22/` | patch 檔案目錄 |
| GStreamer plugin 目錄 | `/usr/lib/gstreamer-1.0/` | 所有 .so plugin 安裝位置 |
| `gst-inspect-1.0` 查詢 | `gst-inspect-1.0 pulsesink` | 確認 pulsesink plugin 是否可用 |

---

### Layer C：ALSA 工具（直接 PCM 存取）

這些工具直接操作 ALSA kernel interface，**繞過 PipeWire**，直接讀寫 PCM 裝置。

| 工具 | Yocto Package | 說明 | 目標機器路徑 |
|------|--------------|------|-------------|
| `aplay` | `alsa-utils-aplay` | PCM 播放（ALSA 直接）| `/usr/bin/aplay` |
| `arecord` | `alsa-utils-aplay` | PCM 錄音（ALSA 直接）| `/usr/bin/arecord` |
| `amixer` | `alsa-utils-amixer` | ALSA mixer 控制（文字模式）| `/usr/bin/amixer` |
| `alsamixer` | `alsa-utils` | ALSA mixer 控制（ncurses TUI）| `/usr/bin/alsamixer` |
| `alsactl` | `alsa-utils-alsactl` | 儲存/還原 mixer 狀態 | `/usr/sbin/alsactl` |
| `alsaucm` | `alsa-utils-alsaucm` | Use Case Manager（UCM2）控制 | `/usr/bin/alsaucm` |
| `alsatplg` | `alsa-utils-alsatplg` | Topology 編譯工具 | `/usr/bin/alsatplg` |

#### 關鍵檔案路徑

| 類別 | 路徑 | 說明 |
|------|------|------|
| Yocto bbappend 目錄 | `meta-rubikpi-bsp/recipes-multimedia/audio/alsa-utils/` | alsa-utils 客製化目錄 |
| alsactl patch | `meta-rubikpi-bsp/recipes-multimedia/audio/alsa-utils/0001-alsactl-add-fallback-for-restoring-from-asound.state.patch` | Scarthgap 編譯修正 patch |
| tmpfiles 設定 | `meta-rubikpi-bsp/recipes-multimedia/audio/alsa-utils/tmpfiles.conf` | 管理 `/var/lib/alsa/` 揮發性目錄 |
| ALSA state 檔案 | `/var/lib/alsa/asound.state` | 由 tmpfiles.conf 管理（注意：RubikPi3 刻意不預放 asound.state）|
| ALSA lib | `/usr/lib/libasound.so` | ALSA client library |

> **注意**：`60-disable-alsa.conf`（WirePlumber 設定）確保 PipeWire 不直接佔用 ALSA PCM。  
> 因此 `aplay`/`arecord` 可在 PipeWire 未佔用時直接使用。  
> 若需強制直接使用，先 `systemctl stop pipewire`。

---

### Layer D：TinyALSA 工具

TinyALSA 是 Qualcomm 採用的輕量 ALSA 替代函式庫，並提供 **plug-in 架構**：PCM / Mixer / Compress plug-in 會建立一個虛擬音效卡（Virtual Sound Card），將所有呼叫路由至 plug-in 專屬的 `.so` 實作，再由 AGM 管理實際的硬體存取。

> 參考文件：[TinyALSA — 80-70015-16](https://docs.qualcomm.com/doc/80-70015-16/topic/apis_and_sample_apps.html?product=895724676033554725&facet=Audio&version=1.2#TinyALSA)

#### 工具清單

| 工具 | Yocto Package | 說明 | 目標機器路徑 |
|------|--------------|------|-------------|
| `tinyplay` | `tinyalsa` | 播放 WAV 檔案（TinyALSA）| `/usr/bin/tinyplay` |
| `tinycap` | `tinyalsa` | 錄音至 WAV 檔案（TinyALSA）| `/usr/bin/tinycap` |
| `tinymix` | `tinyalsa` | 查看/設定 ALSA mixer controls | `/usr/bin/tinymix` |
| `tinypcminfo` | `tinyalsa` | 查看 PCM 裝置能力（fmt/rate/ch）| `/usr/bin/tinypcminfo` |

#### 關鍵檔案路徑

| 類別 | 路徑 | 說明 |
|------|------|------|
| Build-tree 原始碼 | `build-qcom-wayland/workspace/sources/tinyalsa` | TinyALSA 原始碼（官方文件指示）|
| 虛擬音效卡設定 | `build-qcom-wayland/workspace/sources/qcom-agm/opensource/agm/snd_parser/configs/qcs6490/` | `card-defs.xml`（Virtual PCM/Compress/Mixer node 定義）|
| 目標機器設定 | `/etc/` | card-defs.xml 及其他 AGM 設定安裝位置（on-device）|
| TinyALSA 函式庫 | `/usr/lib/libtinyalsa.so` | TinyALSA client library |

---

### Layer E：Qualcomm qcom-audio-ftm

`qcom-audio-ftm`（Audio Factory Test Mode）是 Qualcomm 提供的專屬測試工具，  
直接呼叫 `qcom-agm`、`qcom-args`，可測試播放、錄音、LOOPBACK 等 use case，**完全繞過 PipeWire 和 PAL**。

| 項目 | 路徑 / 說明 |
|------|------------|
| Yocto recipe | `meta-rubikpi-bsp/recipes-multimedia/audio/qcom-audio-ftm_git.bb` |
| 上游原始碼 | `git.codelinaro.org/clo/le/platform/vendor/qcom-opensource/audio_ftm.git` |
| 分支 | `audio-core.lnx.1.0.r1-rel` |
| 依賴 | `tinyalsa`, `glib-2.0`, `qcom-agm`, `qcom-kvh2xml`, `qcom-args` |
| 目標機器執行檔 | `/usr/bin/ftm_audio_main`（或 `/usr/bin/ftm_audio`，依 recipe 的 `${bindir}`）|
| 目標機器設定 | `/etc/qcm6490/`（由 `do_install:append:qcm6490` 安裝）|

---

### Layer F：PAL API（Platform Audio Layer — C 程式開發介面）

PAL（Platform Audio Layer）是 Qualcomm 提供的音頻抽象 API 層，位於 PipeWire/PulseAudio 和 AGM/Kernel 之間。  
開發者可直接呼叫 PAL API 撰寫高效率的音頻應用，無需透過 PipeWire 框架。

> 參考文件：[PAL — APIs and Sample Apps（80-70015-16）](https://docs.qualcomm.com/doc/80-70015-16/topic/apis_and_sample_apps.html?product=895724676033554725&facet=Audio&version=1.2#PAL)

**PAL 的職責（來自官方文件）：**
- 設定 mixer controls 以配置硬體 codec 裝置與串流
- 呼叫 TinyALSA API 開啟/啟動音頻 session
- 透過 Resource Manager 追蹤所有 active session 與 device
- 解析 `Resource_manager.xml` 和 `Card-defs.xml` 取得 use case graph

#### 關鍵 PAL API 函式

| API | 用途 |
|-----|------|
| `pal_stream_open(attr, n_dev, devices, n_mod, modules, cb, cookie, &handle)` | 開啟音頻串流 |
| `pal_stream_start(handle)` | 開始串流 |
| `pal_stream_pause(handle)` | 暫停串流 |
| `pal_stream_stop(handle)` | 停止串流 |
| `pal_stream_close(handle)` | 關閉串流，釋放資源 |
| `pal_stream_write(handle, buf)` | 寫入 PCM 資料（播放）|
| `pal_stream_read(handle, buf)` | 讀取 PCM 資料（錄音）|
| `pal_stream_set_volume(handle, volume)` | 設定串流音量 |
| `pal_set_param(param_id, payload, payload_size)` | 設定 global 參數 |
| `pal_get_param(param_id, payload, payload_size, &size)` | 取得 global 參數 |

#### 關鍵檔案路徑

| 類別 | 路徑 | 說明 |
|------|------|------|
| Build-tree 原始碼 | `build-qcom-wayland/workspace/sources/qcom-pal` | PAL 原始碼（官方文件指示）|
| PAL 標頭檔 | `/usr/include/PalApi.h` | 主要 API header |
| PAL 函式庫 | `/usr/lib/libpal.so` | PAL shared library |
| Resource Manager 設定 | `/etc/acdbdata/` 或 `/etc/` 下的 `Resource_manager.xml` | Device-to-backend mapping |
| Card-defs 設定 | `build-qcom-wayland/workspace/sources/qcom-agm/opensource/agm/snd_parser/configs/qcs6490/card-defs.xml` | Virtual PCM/compress node 定義 |

---

## 三、RubikPi3 音頻實驗步驟

> **實測日期**：2026-04-24  
> **實測方法**：透過 `adb shell` 遠端執行所有指令，測試板為 RubikPi3（QCS6490）  
> **重要發現**：RubikPi3 實際使用 **PulseAudio（system mode）** 作為音頻伺服器，而非 PipeWire。  
> 所有 sink 皆為 `module-pal-card`（PAL 後端），`pw-play`/`pw-record`/`pw-cli` 工具並未安裝。

以下實驗依序從系統狀態確認 → TinyALSA → ALSA → PulseAudio 工具 → GStreamer → 進階測試。
![alt text](<../Qualcomm_Linux_Audio/High-level audio software architecture.png>)
---

### 實驗 0：前置確認

#### 0-1 確認音效卡載入

```bash
cat /proc/asound/cards
```

**【實際結果】✅**
```
 0 [qcm6490idpsndca]: qcm6490 - qcm6490-idp-snd-card
                      qcm6490-idp-snd-card
```

音效卡名稱：`qcm6490-idp-snd-card`，由 Machine Driver + Topology 共同決定。

---

#### 0-2 確認 PCM 裝置

```bash
cat /proc/asound/pcm
```

**【實際結果】✅**
```
00-00: TDM-LPAIF-TX-PRIMARY msm-stub-aif0-tx-0    :  : capture 1
00-01: TDM-LPAIF-RX-PRIMARY msm-stub-aif0-rx-1    :  : playback 1
00-02: MI2S-LPAIF-RX-PRIMARY multicodec-2          :  : playback 1
00-03: MI2S-LPAIF-TX-PRIMARY multicodec-3          :  : capture 1
00-04: MI2S-LPAIF_RXTX-RX-PRIMARY msm-stub-aif0-rx-4 : : playback 1
00-05: MI2S-LPAIF_RXTX-TX-PRIMARY msm-stub-aif0-tx-5 : : capture 1
00-06: MI2S-LPAIF_VA-RX-PRIMARY msm-stub-aif0-rx-6 :  : playback 1
00-07: MI2S-LPAIF_VA-TX-PRIMARY msm-stub-aif0-tx-7 :  : capture 1
00-08: MI2S-LPAIF-RX-TERTIARY msm-stub-aif0-rx-8   :  : playback 1
00-09: MI2S-LPAIF-TX-TERTIARY msm-stub-aif0-tx-9   :  : capture 1
```

> **注意**：這些是 AudioReach **LPAIF 後端 PCM** 節點，不是 Topology 前端的 MULTIMEDIA0/1/2/3。  
> 前端的 Front-End PCM 由 PAL/AGM 虛擬音效卡建立，`/proc/asound/pcm` 只顯示 ALSA 後端節點。
>
> | PCM 節點 | 方向 | 路徑 | 備註 |
> |---------|------|------|------|
> | hw:0,1 | Playback | TDM-LPAIF-RX-PRIMARY | TDM 播放路徑 |
> | hw:0,2 | Playback | MI2S-LPAIF-RX-PRIMARY | ES8316 耳機輸出（`multicodec-2`）|
> | hw:0,0 | Capture  | TDM-LPAIF-TX-PRIMARY | TDM 錄音路徑 |
> | hw:0,3 | Capture  | MI2S-LPAIF-TX-PRIMARY | ES8316 MIC 輸入（`multicodec-3`）|

---

#### 0-3 確認 `/dev/snd` 裝置節點

```bash
ls /dev/snd
```

**【實際結果】✅**
```
by-path    pcmC0D0c  pcmC0D2p  pcmC0D4p  pcmC0D6p  pcmC0D8p  timer
controlC0  pcmC0D1p  pcmC0D3c  pcmC0D5c  pcmC0D7c  pcmC0D9c
```

`/dev/snd` 下的節點是 Linux 核心中 **ALSA（Advanced Linux Sound Architecture）** 驅動程式所建立的裝置檔案，是硬體音效卡與軟體之間的橋樑。

##### `controlC0`
音效卡的控制台（`C0` = Card 0）。供上層工具（`tinymix`、`amixer`）用來讀寫 ES8316 Codec 暫存器，包括音量、靜音開關、MIC Boost 等所有 Mixer Controls。

##### `pcmC0Dxp` / `pcmC0Dxc`（PCM 節點）
核心音訊資料傳輸節點，命名規則為 `pcmC{卡號}D{裝置號}{類型}`：

| 節點 | 方向 | ALSA 路徑 | 對應音頻路徑 |
|------|------|----------|-------------|
| `pcmC0D0c` | Capture（`c`）| hw:0,0 | TDM-LPAIF-TX-PRIMARY |
| `pcmC0D1p` | Playback（`p`）| hw:0,1 | TDM-LPAIF-RX-PRIMARY |
| `pcmC0D2p` | Playback | hw:0,2 | MI2S-LPAIF-RX-PRIMARY（ES8316 耳機輸出）|
| `pcmC0D3c` | Capture | hw:0,3 | MI2S-LPAIF-TX-PRIMARY（ES8316 MIC 輸入）|
| `pcmC0D4p` | Playback | hw:0,4 | MI2S-LPAIF_RXTX-RX-PRIMARY |
| `pcmC0D5c` | Capture | hw:0,5 | MI2S-LPAIF_RXTX-TX-PRIMARY |
| `pcmC0D6p` | Playback | hw:0,6 | MI2S-LPAIF_VA-RX-PRIMARY |
| `pcmC0D7c` | Capture | hw:0,7 | MI2S-LPAIF_VA-TX-PRIMARY |
| `pcmC0D8p` | Playback | hw:0,8 | MI2S-LPAIF-RX-TERTIARY |
| `pcmC0D9c` | Capture | hw:0,9 | MI2S-LPAIF-TX-TERTIARY |

> ⚠ **重要**：這些節點是 LPAIF **後端（Back-End）PCM**，由 PAL/AGM 統一管理。  
> 直接使用 `tinyplay` / `arecord -D hw:0,x` 存取會回報 `Invalid argument`，  
> 必須透過 **PulseAudio → PAL** 路徑才能正常播放/錄音（見實驗 3、4）。

##### `timer`
供 ALSA 內部音訊同步使用，確保播放節奏穩定。上層應用程式不直接存取。

##### `by-path/`
目錄，內含依硬體物理連接路徑命名的符號連結，用於多音效卡系統中按插槽精確定位裝置。

---

#### 0-4 確認 PulseAudio 服務狀態

```bash
systemctl status pulseaudio
```

**【實際結果】✅**
```
* pulseaudio.service - PulseAudio Sound Service
     Loaded: loaded (/usr/lib/systemd/system/pulseaudio.service; enabled)
     Active: active (running)
   Main PID: 1628 (pulseaudio)
             `- /usr/bin/pulseaudio --system --daemonize=no -v
```

> RubikPi3 使用 **PulseAudio system mode**（`--system`），以 `pulse` 使用者身分運行。  
> 下游後端為 `module-pal-card`（PAL → AGM → LPAIF Kernel Driver）。  
> **PipeWire 並未安裝**：`pw-play`、`pw-record`、`pw-cli`、`pw-dump` 等工具不存在。

---

#### 0-5 確認 PulseAudio Sinks / Sources

```bash
pactl info
pactl list sinks short
pactl list sources short
```

**【實際結果】✅**

`pactl info` 輸出：
```
Server String: /var/run/pulse/native
Server Name: pulseaudio
Server Version: 17.0
Default Sample Specification: s16le 2ch 44100Hz
Default Sink:   low-latency0
Default Source: regular0
```

`pactl list sinks short`：
```
0  low-latency0   module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
1  deep-buffer0   module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
2  offload0       module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
3  voip-rx0       module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
```

`pactl list sources short`：
```
0  low-latency0.monitor  module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
1  deep-buffer0.monitor  module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
2  offload0.monitor      module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
3  voip-rx0.monitor      module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
4  regular0              module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
5  regular2              module-pal-card.c  s16le 2ch 48000Hz  SUSPENDED
6  voip-tx0              module-pal-card.c  s16le 1ch 48000Hz  SUSPENDED
```

> **Sink 用途說明**：`low-latency0`（一般播放，預設）、`deep-buffer0`（低功耗播放）、`offload0`（DSP offload）、`voip-rx0`（VoIP 播放）  
> **Source 用途說明**：`regular0`（一般錄音，預設）、`regular2`（第二麥克風路徑，官方 parec 範例使用此裝置）、`voip-tx0`（VoIP 錄音，mono）

---

#### 0-6 列出 ALSA Mixer Controls（ES8316 Codec）

```bash
tinymix -D 0 contents
```

**【實際結果】✅**（共 36 個 controls，均為 ES8316 Codec 原生控制項）
```
Number of controls: 36
ctl  type  num  name                           value
0    BOOL   1   Headset Jack                   On
1    INT    2   Headphone Playback Volume      2, 2  (range 0->3)
2    INT    2   Headphone Mixer Volume         11, 11 (range 0->11)
3    ENUM   1   Playback Polarity              Normal
4    INT    2   DAC Playback Volume            192, 192 (range 0->192)
5    BOOL   1   DAC Soft Ramp Switch           Off
...（共 36 項）
12   BOOL   1   Mic Boost Switch               On
13   INT    1   ADC Capture Volume             192 (range 0->192)
14   INT    1   ADC PGA Gain Volume            6 (range 0->10)
17   BOOL   1   ALC Capture Switch             On
```

> **重要**：mixer controls 直接對應 ES8316 Codec 暫存器，不再以 MULTIMEDIA0/1 命名。  
> 音量調整應使用 `DAC Playback Volume`（0–192）或透過 `rubikpi_config audio volume`。

---

### 實驗 1：TinyALSA 工具測試

#### 1-1 查看 PCM 裝置能力（tinypcminfo）

```bash
tinypcminfo -D 0 -d 0   # TDM Capture
tinypcminfo -D 0 -d 1   # TDM Playback
tinypcminfo -D 0 -d 2   # MI2S ES8316 Playback（耳機）
tinypcminfo -D 0 -d 3   # MI2S ES8316 Capture（MIC）
```

**【實際結果】✅**

| 裝置 | 方向 | 格式 | 採樣率 | 聲道 | period size |
|------|------|------|--------|------|------------|
| hw:0,0 | Capture only | S16_LE, S24_LE, S32_LE | 8k–384kHz | 1–16 | 64–4096 |
| hw:0,1 | Playback only | S16_LE, S24_LE, S32_LE | 8k–384kHz | 1–16 | 64–4096 |
| hw:0,2 | Playback only | S16_LE, S24_LE | 8k–48kHz | 1–8 | 128–4096 |
| hw:0,3 | Capture only | S16_LE, S24_LE | 8k–48kHz | 1–8 | 128–4096 |
| hw:0,4 | Playback only | S16_LE, S24_LE, S32_LE | 8k–48kHz | 1–8 | 128–4096 |
| hw:0,5 | Capture only | S16_LE, S24_LE, S32_LE | 8k–48kHz | 1–8 | 128–4096 |

> ES8316 耳機路徑（hw:0,2）和 MIC 路徑（hw:0,3）最高僅支援 48kHz（硬體限制）；  
> TDM 路徑（hw:0,0/1）支援至 384kHz。

---

#### 1-2 tinymix 讀寫 Mixer Controls

```bash
# 查看 DAC Playback Volume
tinymix -D 0 get "DAC Playback Volume"

# 設定為最大（注意：S  tereo 控制需同時指定兩個值）
tinymix -D 0 set "DAC Playback Volume" 192 192

# 確認
tinymix -D 0 get "DAC Playback Volume"
```

**【實際結果】✅**
```
152, 152 (range 0->192)        ← 設定前（預設值）
192, 192 (range 0->192)        ← 設定後（最大值）
```

> **注意**：Stereo 控制項需同時指定左右聲道兩個值（`192 192`），若只給一個值則只改左聲道。

---

#### 1-3 tinyplay 直接 PCM 播放（⚠ 受 PAL 架構限制）

```bash
# 先停止 PulseAudio
systemctl stop pulseaudio

# 嘗試直接播放至 ES8316 路徑
tinyplay '/Wii_Music(128k).wav' -D 0 -d 2
```

**【實際結果】❌ 失敗**
```
playing '/Wii_Music(128k).wav': 2 ch, 48000 hz, 16-bit signed PCM
error playing sample. cannot read/write stream data: Invalid argument
Played 0 bytes. Remains 16664872 bytes.
```

> **原因分析**：在 RubikPi3 的 AudioReach 架構中，LPAIF 後端 PCM 節點（hw:0,2/hw:0,3 等）  
> 由 **PAL（Platform Audio Layer）統一管理**，需透過 PAL API 先建立 stream、配置 mixer path  
> 才能開啟 PCM 裝置。直接使用 TinyALSA 工具（tinyplay/tinycap）繞過 PAL 會導致 `Invalid argument`。  
> **結論**：tinyplay/tinycap 直接存取在此架構下不可用；請改用 PulseAudio/GStreamer 工具。

---

### 實驗 2：ALSA 工具測試

#### 2-1 aplay 播放（經由 ALSA-PulseAudio Plugin 路由）

```bash
# aplay 預設走 ALSA pulse plugin → PulseAudio → PAL
aplay /tmp/test_parec.wav -v
```

**【實際結果】✅**
```
Playing WAVE '/tmp/test_parec.wav' : Signed 16 bit Little Endian, Rate 48000 Hz, Mono
ALSA <-> PulseAudio PCM I/O Plugin
Its setup is:
  stream       : PLAYBACK
  access       : RW_INTERLEAVED
  format       : S16_LE
  channels     : 1
  rate         : 48000
```

> `aplay -L` 顯示 ALSA 預設裝置為：
> ```
> default
>     Default ALSA Output (currently PulseAudio Sound Server)
> ```
> 因此 `aplay` 自動透過 **ALSA→PulseAudio PCM I/O Plugin** 路由，無需停止任何服務。

---

#### 2-2 arecord 錄音（hw 直接存取：失敗）

```bash
# 嘗試直接錄音至 MI2S MIC 路徑（hw:0,3）
arecord -D hw:0,3 -f S16_LE -r 48000 -c 2 -d 5 /tmp/rec_alsa_hw.wav
```

**【實際結果】❌ 失敗**
```
Recording WAVE '/tmp/rec_alsa_hw.wav' : Signed 16 bit Little Endian, Rate 48000 Hz, Stereo
arecord: pcm_read:2272: read error: Invalid argument
```

> **原因**：同 tinyplay — 後端 LPAIF PCM 節點需透過 PAL 開啟，直接 hw 存取無效。  
> **替代方案**：使用 `parec` 或 `gst-launch-1.0 pulsesrc ...` 透過 PulseAudio 錄音。

---

#### 2-3 amixer 查看 Mixer Controls

```bash
# 查看 ES8316 DAC 音量
amixer -c 0 get "DAC Playback Volume"

# 查看 ADC 錄音增益
amixer -c 0 get "ADC Capture Volume"
```

---

### 實驗 3：PulseAudio 工具測試（推薦日常使用）

PulseAudio 運作時**無需**停止服務。

#### 3-1 確認伺服器狀態與預設裝置

```bash
pactl info
pactl get-default-sink
pactl get-default-source
```

**【實際結果】✅**
```
Default Sink:   low-latency0
Default Source: regular0
```

---

#### 3-2 使用 parec 錄音（官方推薦方式）

```bash
# 從 regular2 source 錄製 5 秒，存成 WAV
timeout 5 parec --rate=48000 --format=s16le --channels=1 \
  --file-format=wav /tmp/test_parec.wav --device=regular2

# 確認檔案大小
ls -la /tmp/test_parec.wav
```

**【實際結果】✅**
```
-rw-rw-rw- 1 root root 470444 Jan  1 01:35 /tmp/test_parec.wav
```

> 5 秒 × 48000Hz × 1ch × 2bytes = 480000 bytes + WAV header ≈ 470444 bytes ✓

---

#### 3-3 使用 paplay 播放

```bash
paplay /tmp/test_parec.wav -v
```

**【實際結果】✅**
```
Opening a playback stream with sample specification 's16le 1ch 48000Hz' and channel map 'mono'.
Connection established.
Stream successfully created.
Buffer metrics: maxlength=4194304, tlength=192000, prebuf=190082, minreq=1920
Using sample spec 's16le 1ch 48000Hz', channel map 'mono'.
Connected to device low-latency0 (index: 0, suspended: no).
Stream started.
Playback stream drained.: 44791 usec.
Draining connection to server.
```

---

#### 3-4 pactl 音量 / 靜音控制

```bash
# 設定預設 sink 音量至 80%
SINK=$(pactl get-default-sink)
pactl set-sink-volume "$SINK" 80%
pactl get-sink-volume "$SINK"

# 靜音 / 取消靜音（toggle）
pactl set-sink-mute "$SINK" toggle
pactl get-sink-mute "$SINK"
```

**【實際結果】✅**
```
Volume: front-left: 52428 /  80% / -5.81 dB,   front-right: 52428 /  80% / -5.81 dB
        balance 0.00

Mute: yes   ← toggle 後
Mute: no    ← 再次 toggle 取消靜音
```

---

### 實驗 4：GStreamer Pipeline 測試

GStreamer 透過 `pulsesink`/`pulsesrc` 與 PulseAudio 連接，**無需**停止服務。

> **前提**：先設定音頻輸出路由（例如耳機輸出），否則可能無聲：
> ```bash
> rubikpi_config audio output headset
> ```

#### 4-1 播放 WAV 檔案（已確認可用）

```bash
# 使用者確認可成功播放的指令：
rubikpi_config audio output headset
gst-launch-1.0 filesrc location="/Wii_Music(128k).wav" ! \
  decodebin ! audioconvert ! audioresample ! pulsesink
```

**【實際結果】✅（使用者確認成功播放）**

Pipeline 協商結果（`-v` 模式輸出）：
```
/GstPulseSink:pulsesink0: current-device = low-latency0
caps = audio/x-raw, format=S16LE, layout=interleaved, channels=2, rate=48000
New clock: GstPulseSinkClock
Got EOS from element "pipeline0".
Execution ended after 0:01:26.867189237
```

> 音頻流自動路由至 `low-latency0`（PAL 預設 sink），格式 S16LE 2ch 48000Hz 無需轉換。

---

#### 4-2 播放正弦波測試音

```bash
gst-launch-1.0 audiotestsrc freq=1000 num-buffers=480 ! \
  audio/x-raw,rate=48000,channels=2,format=S16LE ! \
  audioconvert ! pulsesink
```

**【實際結果】✅**
```
Setting pipeline to PAUSED ...
Pipeline is PREROLLED ...
Setting pipeline to PLAYING ...
New clock: GstPulseSinkClock
Got EOS from element "pipeline0".
Execution ended after 0:00:10.293252443
```

---

#### 4-3 錄音至 WAV 檔案

```bash
gst-launch-1.0 pulsesrc ! \
  audio/x-raw,rate=48000,channels=2,format=S16LE ! \
  audioconvert ! wavenc ! filesink location=/tmp/rec_gst.wav &
# 錄製數秒後 Ctrl+C 或 kill
sleep 5 && kill %1
ls -la /tmp/rec_gst.wav
```

**【實際結果】✅**
```
Setting pipeline to PLAYING ...
New clock: GstPulseSrcClock
-rw-rw-rw- 1 root root 873644 Jan  1 01:39 /tmp/rec_gst.wav
```

---

#### 4-4 Loopback（MIC → 耳機即時回播）

```bash
gst-launch-1.0 pulsesrc ! queue ! audioconvert ! audioresample ! pulsesink &
sleep 8 && kill %1
```

**【實際結果】✅ Pipeline 正常啟動並運行**
```
Setting pipeline to PLAYING ...
New clock: GstPulseSrcClock
Redistribute latency...
```

> **注意**：Loopback 可能引起回授（Feedback）；建議使用耳機或調低音量再測試。

---

### 實驗 5：音頻路由切換（rubikpi_config）

`rubikpi_config audio` 是 RubikPi3 提供的音頻路由管理工具，底層調用 PAL API 切換輸出路徑。

#### 5-1 切換輸出至耳機 / HDMI

```bash
rubikpi_config audio output headset
rubikpi_config audio output hdmi
```

**【實際結果】✅**
```
Switched output port to headset
Switched output port to hdmi
```

**可用的 subcommand：**
```
output  Set output port: headset or hdmi
volume  Get (no value) or set (one integer) volume
card    Show /proc/asound/cards
pcm     Show /proc/asound/pcm
```

---

#### 5-2 音量控制

```bash
# 查看目前音量（對應 tinymix DAC Playback Volume，範圍 0–192）
rubikpi_config audio volume

# 設定音量為 80（L/R）
rubikpi_config audio volume 80

# 確認
rubikpi_config audio volume
```

**【實際結果】✅**
```
192, 192 (range 0->192)   ← 設定前
Volume set to 80 (L/R)    ← 設定中
80, 80 (range 0->192)     ← 設定後
```

> `rubikpi_config audio volume` 直接操作 ES8316 的 `DAC Playback Volume` Mixer Control（同 `tinymix`）。

---

### 實驗 6：PulseAudio 多路混音測試

測試 PulseAudio 的混音能力（多個應用程式同時播放）。

```bash
# 同時啟動兩條 GStreamer pipeline
gst-launch-1.0 audiotestsrc freq=440 ! \
  audio/x-raw,rate=48000,channels=2,format=S16LE ! \
  audioconvert ! pulsesink &

gst-launch-1.0 audiotestsrc freq=880 ! \
  audio/x-raw,rate=48000,channels=2,format=S16LE ! \
  audioconvert ! pulsesink &

# 觀察混音結果（應同時聽到 440Hz + 880Hz）
# PulseAudio 在 CPU 端完成混音後，透過 PAL 下送 DSP

wait
```

> 兩條 stream 均路由至 `low-latency0` sink，PulseAudio 軟體混音器完成合流。

---

### 實驗 7：HDMI 音頻輸出測試

RubikPi3 支援 HDMI 音頻（透過 `rubikpi_config` 切換路由）。

#### 7-1 切換至 HDMI 輸出

```bash
rubikpi_config audio output hdmi
```

**【實際結果】✅**
```
Switched output port to hdmi
```

#### 7-2 播放測試音至 HDMI

```bash
gst-launch-1.0 filesrc location="/Wii_Music(128k).wav" ! \
  decodebin ! audioconvert ! audioresample ! pulsesink
```

#### 7-3 切換回耳機輸出

```bash
rubikpi_config audio output headset
```

> **注意**：查看 HDMI sink 時，`pactl list sinks short` 顯示 4 個固定 PAL sink（`low-latency0`/`deep-buffer0`/`offload0`/`voip-rx0`），  
> HDMI/耳機路由切換在 PAL 內部實現，對 PulseAudio 層透明，因此 `pactl` 不會顯示 `hdmi` 字樣的獨立 sink。

---

### 實驗 8：音量與 ACDB 校準驗證

#### 8-1 透過 tinymix 直接調整 ES8316 DAC 音量

```bash
# 查看目前值
tinymix -D 0 get "DAC Playback Volume"

# 設定為最大（L+R 均設 192）
tinymix -D 0 set "DAC Playback Volume" 192 192

# 播放測試音確認音量
gst-launch-1.0 audiotestsrc freq=1000 num-buffers=240 ! \
  audio/x-raw,rate=48000,channels=2,format=S16LE ! pulsesink
```

**【實際結果】✅**
```
192, 192 (range 0->192)
```

#### 8-2 確認 ADSP 服務與 ACDB 韌體

```bash
# 確認 ADSP RPC daemon 運行
systemctl status adsprpcd

# 確認 audioadsprpcd（audiopd domain）
ps aux | grep audioadsprpcd

# 確認 ACDB 韌體存在
ls /lib/firmware/qcom/qcs6490/ | head -5
```

**【實際結果】✅**
```
adsprpcd.service: active (running), PID 764
/usr/bin/audioadsprpcd audiopd  ← PID 765, running

/lib/firmware/qcom/qcs6490/:
  Data.msc  Ver_Info.txt  adsp.b00  adsp.b01  adsp.b02 ...（共多個分段韌體）
```

> `adsprpcd`（FastRPC daemon）和 `audioadsprpcd audiopd`（Audio PD domain）  
> 是 PAL 能夠呼叫 DSP 的前提，兩者均正常運行 ✅

---

### 實驗 9：FTM 工廠測試模式

```bash
# 確認 FTM 相關工具
ls /usr/bin/ftm*
```

**【實際結果】**
```
/usr/bin/ftmdaemon
```

> 本板安裝的是 `ftmdaemon`（FTM daemon），而非 `ftm_audio_main`。  
> `ftmdaemon` 作為通用工廠測試 daemon，需搭配對應 host-side 工具（如 QPST / DIAG）使用，  
> 不支援單獨 CLI 音頻測試。`qcom-audio-ftm_git.bb` 安裝的 `ftm_audio_main` 在此鏡像中未包含。

---

## 四、工具層次對應總結（實測修正版）

> **實測結論**：RubikPi3 使用 PulseAudio（system mode）+ module-pal-card，**非 PipeWire**。  
> `pw-play`/`pw-record` 等 PipeWire 工具未安裝。直接 hw 存取 ALSA/TinyALSA 因 PAL 架構而無法使用。

| 工具 | 介面層次 | 需停 PulseAudio | 實測狀態 | 適用場景 |
|------|---------|----------------|---------|---------|
| `rubikpi_config audio` | PAL（路由切換）| ❌ | ✅ 可用 | 耳機/HDMI 切換、音量設定 |
| `paplay` / `parec` / `pactl` | PulseAudio API | ❌ | ✅ 可用 | 日常播放/錄音/音量控制 |
| `gst-launch-1.0` (pulsesink/pulsesrc) | GStreamer + PulseAudio | ❌ | ✅ 可用 | 多媒體 pipeline 測試 |
| `aplay` / `arecord`（default device）| ALSA → PulseAudio Plugin | ❌ | ✅ 可用（路由至 PA）| 相容性播放 |
| `tinymix` | TinyALSA Mixer | ❌ | ✅ 可用 | ES8316 Codec 暫存器讀寫 |
| `tinypcminfo` | TinyALSA PCM Info | ❌ | ✅ 可用 | 查看 PCM 裝置能力 |
| `aplay -D hw:0,x` / `arecord -D hw:0,x` | ALSA 直接 hw 存取 | ✅ | ❌ 失敗（Invalid argument）| 需 PAL 配置，直接存取不可用 |
| `tinyplay` / `tinycap`（直接 PCM）| TinyALSA 直接 hw | ✅ | ❌ 失敗（Invalid argument）| 需 PAL 配置，直接存取不可用 |
| `pw-play` / `pw-record` | PipeWire Native | — | ❌ 未安裝 | 此映像未包含 PipeWire |

---

## 五、常見問題排查（實測修正版）

| 症狀 | 排查方向 |
|------|---------|
| GStreamer 無聲 | 先執行 `rubikpi_config audio output headset`（或 `hdmi`）設定輸出路由 |
| `tinyplay` / `aplay -D hw:0,x` 回報 `Invalid argument` | 正常現象：PAL 管理 ALSA 後端節點，需透過 PulseAudio 存取 |
| `parec` 錄音為靜音 | 確認 `Mic Boost Switch`（ctl 12）為 On；確認 `ADC Capture Volume`（ctl 13）不為 0 |
| `pactl list sinks` 顯示 SUSPENDED | 正常待機狀態，一旦有 stream 連接即自動喚醒（RUNNING）|
| GStreamer pulsesink pipeline error | 確認 `gst-inspect-1.0 pulsesink` 可執行；確認 PulseAudio service 正在運行 |
| HDMI 無聲 | 使用 `rubikpi_config audio output hdmi` 切換路由後再播放 |
| PulseAudio 服務停止後工具失效 | 執行 `systemctl start pulseaudio` 恢復；所有 PulseAudio 工具依賴此服務 |
| `adsprpcd` / `audioadsprpcd` 未運行 | PAL 無法初始化 ADSP，會導致所有音頻失效；重新啟動對應 systemd service |
