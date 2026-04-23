# QCM6490 ASoC Machine Driver 分析

原始碼路徑：`sound/soc/qcom/qcm6490.c`  
GitHub：https://github.com/rubikpi-ai/linux/blob/main/sound/soc/qcom/qcm6490.c

---

## 驅動概覽

| 項目 | 說明 |
|------|------|
| 驅動名稱 | `qcm6490` |
| compatible | `qcom,qcm6490-sndcard` |
| 功能 | ASoC machine driver — 管理 MI2S 時鐘、DAI 格式、Jack 偵測 |
| Copyright | Qualcomm Innovation Center, Inc. 2023-2025 |

---

## 關鍵常數

```c
#define DEFAULT_MCLK_RATE    24576000   /* ES8316 MCLK = 24.576 MHz */
#define TDM_BCLK_RATE         6144000   /* TDM Bit Clock */
#define MI2S_BCLK_RATE        1536000   /* MI2S Bit Clock = 1.536 MHz */
```

---

## 私有資料結構

```c
struct qcm6490_snd_data {
    struct qcom_snd_common_data common_priv;
    bool stream_prepared[AFE_PORT_MAX];
    struct snd_soc_card *card;

    /* MI2S 時鐘計數器 (reference counting) */
    uint32_t pri_mi2s_clk_count;    /* PRIMARY MI2S BCLK 計數 */
    uint32_t sec_mi2s_clk_count;
    uint32_t quat_mi2s_clk_count;
    uint32_t tert_mi2s_clk_count;
    uint32_t quin_mi2s_clk_count;
    uint32_t quat_tdm_clk_count;
    uint32_t pri_mi2s_mclk_count;   /* PRIMARY MI2S MCLK 計數 (ES8316 特有) */

    /* SoundWire 串流 */
    struct sdw_stream_runtime *sruntime[AFE_PORT_MAX];

    /* Jack 偵測 */
    struct snd_soc_jack jack;
    bool jack_setup;
    struct snd_soc_jack hdmi_jack[8];

    bool tert_formats_high_bit;
};
```

---

## 核心函式說明

### `qcm6490_mi2s_mclk_init()` — MCLK 永久開啟設計

```c
/* 原始碼注釋：
   The ES8316 IC requires MCLK to be constantly on.
   If MCLK switches on and off as playback starts and stops,
   it can easily cause POP sound */
static int qcm6490_mi2s_mclk_init(struct snd_soc_pcm_runtime *rtd)
{
    switch (cpu_dai->id) {
    case PRIMARY_MI2S_RX:
    case PRIMARY_MI2S_TX:
        if (++(data->pri_mi2s_mclk_count) == 1) {
            /* 只在第一個串流開啟時設置 MCLK，之後不再關閉 */
            snd_soc_dai_set_sysclk(cpu_dai,
                Q6AFE_LPASS_CLK_ID_MCLK_1,
                DEFAULT_MCLK_RATE,          /* 24.576 MHz */
                SNDRV_PCM_STREAM_PLAYBACK);
        }
        break;
    }
}
```

**設計要點：**
- 使用 `pri_mi2s_mclk_count` 做參考計數
- 只在計數從 0 → 1 時啟動 MCLK
- MCLK 一旦啟動就不停止（避免 POP 聲）
- 在 `qcm6490_snd_init()` 的 `PRIMARY_MI2S_RX/TX` 分支呼叫

---

### `qcm6490_snd_startup()` — 串流啟動時設定 BCLK

```c
static int qcm6490_snd_startup(struct snd_pcm_substream *substream)
{
    unsigned int fmt           = SND_SOC_DAIFMT_BP_FP;   /* CPU = provider */
    unsigned int codec_dai_fmt = SND_SOC_DAIFMT_BC_FC;   /* Codec = consumer */

    switch (cpu_dai->id) {
    case PRIMARY_MI2S_RX:
    case PRIMARY_MI2S_TX:
        codec_dai_fmt |= SND_SOC_DAIFMT_NB_NF;  /* 正常 bit/frame 極性 */
        if (++(data->pri_mi2s_clk_count) == 1) {
            /* 啟動 BCLK (Bit Clock)，頻率 1.536 MHz */
            snd_soc_dai_set_sysclk(cpu_dai,
                Q6AFE_LPASS_CLK_ID_PRI_MI2S_IBIT,
                MI2S_BCLK_RATE,
                SNDRV_PCM_STREAM_PLAYBACK);
        }
        snd_soc_dai_set_fmt(cpu_dai, fmt);           /* CPU: provider */
        snd_soc_dai_set_fmt(codec_dai, codec_dai_fmt); /* Codec: consumer */
        break;
    /* ... 其他 MI2S 介面 ... */
    }
}
```

**重要：BCLK vs MCLK 管理方式不同**
- MCLK (24.576 MHz)：永久開啟，在 `init()` 階段設置
- BCLK (1.536 MHz)：串流期間開啟，在 `startup()` / `shutdown()` 管理

---

### `qcm6490_snd_shutdown()` — 串流結束時關閉 BCLK

```c
static void qcm6490_snd_shutdown(struct snd_pcm_substream *substream)
{
    switch (cpu_dai->id) {
    case PRIMARY_MI2S_RX:
    case PRIMARY_MI2S_TX:
        if (--(data->pri_mi2s_clk_count) == 0) {
            /* 所有串流結束後關閉 BCLK */
            snd_soc_dai_set_sysclk(cpu_dai,
                Q6AFE_LPASS_CLK_ID_PRI_MI2S_IBIT,
                0,   /* 頻率設 0 = 停用 */
                SNDRV_PCM_STREAM_PLAYBACK);
        }
        break;
    /* MCLK 不在這裡關閉！ */
    }
}
```

---

### `qcm6490_be_hw_params_fixup()` — 強制 Backend 參數

```c
static int qcm6490_be_hw_params_fixup(...)
{
    rate->min = rate->max = 48000;   /* 強制 48 kHz */
    channels->min = 2;
    channels->max = 2;               /* 強制雙聲道 */
    /* TX 路徑允許單聲道 */
    case TX_CODEC_DMA_TX_0/1/2/3:
        channels->min = 1;
}
```

---

### `qcm6490_snd_init()` — 各 DAI 的初始化

```c
switch (cpu_dai->id) {
case PRIMARY_MI2S_RX:
case PRIMARY_MI2S_TX:
    return qcm6490_mi2s_mclk_init(rtd);   /* ← ES8316 MCLK 設置 */

case TX_CODEC_DMA_TX_3:
case RX_CODEC_DMA_RX_0:
    ret = qcom_snd_wcd_jack_setup(rtd, &data->jack, &data->jack_setup);
    break;

case DISPLAY_PORT_RX_0:
case DISPLAY_PORT_RX_1:
    /* HDMI Jack 設置 */
    ...
}
```

---

### `qcm6490_add_be_ops()` — 套用 Backend ops

```c
static void qcm6490_add_be_ops(struct snd_soc_card *card)
{
    for_each_card_prelinks(card, i, link) {
        /* 只對非 dummy codec 的鏈路套用 */
        if ((link->num_codecs != 1) ||
            strcmp(link->codecs->dai_name, "snd-soc-dummy-dai")) {
            link->init = qcm6490_snd_init;
            link->be_hw_params_fixup = qcm6490_be_hw_params_fixup;
            link->ops = &qcm6490_be_ops;
        }
    }
}
```

---

## DAPM Widgets

```c
static const struct snd_soc_dapm_widget qcm6490_dapm_widgets[] = {
    SND_SOC_DAPM_HP("Headphone Jack", NULL),
    SND_SOC_DAPM_MIC("Mic Jack", NULL),
    SND_SOC_DAPM_PINCTRL("STUB_AIF0_PINCTRL", "stub_aif0_active", "stub_aif0_sleep"),
    SND_SOC_DAPM_PINCTRL("STUB_AIF1_PINCTRL", "stub_aif1_active", "stub_aif1_sleep"),
    SND_SOC_DAPM_PINCTRL("STUB_AIF2_PINCTRL", "stub_aif2_active", "stub_aif2_sleep"),
    SND_SOC_DAPM_PINCTRL("STUB_AIF3_PINCTRL", "stub_aif3_active", "stub_aif3_sleep"),
};
```

---

## OF Match Table — 支援的 compatible 字串

| compatible | card data |
|-----------|-----------|
| `qcom,qcm6490-sndcard` | `qcm6490_data` (RubikPi 3 使用這個) |
| `qcom,qcs6490-rb3gen2-sndcard` | `qcs6490_rb3gen2_data` |
| `qcom,qcs6490-rb3gen2-ia-sndcard` | `qcs6490_rb3gen2_ia_data` |
| `qcom,qcs6490-rb3gen2-ptz-sndcard` | `qcs6490_rb3gen2_ptz_data` |
| `qcom,qcs6490-rb3gen2-video-sndcard` | `qcs6490_rb3gen2_video_data` |
| `qcom,qcs6490-rb3gen2-vision-sndcard` | `qcs6490_rb3gen2_vision_data` |

---

## Platform Probe 流程

```c
qcm6490_platform_probe()
  ├── of_device_get_match_data()    /* 從 DT 取得 card 資料結構 */
  ├── devm_kzalloc()                /* 分配私有資料 */
  ├── qcom_snd_parse_of_v2()        /* 解析 DT 中的 DAI links */
  ├── qcm6490_add_be_ops()          /* 套用 backend ops */
  └── devm_snd_soc_register_card()  /* 向 ASoC 框架登錄 sound card */
```

---

## 整體音頻框架 (ASoC Stack)

```
Userspace (alsa-lib / pulseaudio / pipewire)
     ↕ ALSA PCM API
ALSA Core (pcm_native.c)
     ↕
ASoC Framework (soc-core.c)
     ↕
Machine Driver: qcm6490.c              ← 本文件
 ├── CPU DAI: q6afe (q6afe-dai.c)
 │    └── ADSP Q6 DSP via QMI/APR
 └── Codec DAI: es8316.c               ← es8316_driver_analysis.md
      └── ES8316 IC (via I2C + I2S)
```

---

## 重要設計決策

| 決策 | 說明 |
|------|------|
| MCLK 永久開啟 | 防止 ES8316 POP 聲，在第一個串流 init 時啟動，不關閉 |
| BCLK 動態管理 | 只在串流期間開啟，使用 reference count 防止多串流競爭 |
| hw_params fixup | 強制 48kHz / 2ch，確保 DSP backend 格式一致 |
| DT 驅動 | 使用 `qcom_snd_parse_of_v2()` 從 DT 動態建立 DAI links |
