# RubikPi 3 Audio Stack 文件

[RubikPi AI](https://rubikpi.ai/)
![RubikPi3 開發板](RubikPi3/RubikPi3_Dev.jpg)



RubikPi 3 相關 GitHub 函式庫：
- https://github.com/rubikpi-ai/linux
- https://github.com/rubikpi-ai/linux-android13
- https://github.com/rubikpi-ai/linux-debian
- https://github.com/rubikpi-ai/meta-rubikpi-bsp
- https://github.com/rubikpi-ai/meta-rubikpi-distro
- https://github.com/rubikpi-ai/device-tree

---

## 硬體概覽

| 項目 | 內容 |
|------|------|
| SoC | Qualcomm QCS6490 (基於 SC7280 架構) |
| 音頻 Codec | Everest Semiconductor ES8316 |
| I2C 地址 | 0x11 (i2c0 總線) |
| I2S 接口 | PRIMARY MI2S (Playback + Capture) |
| MCLK | LPASS MCLK1，頻率 24.576 MHz (永久開啟) |
| Jack IRQ | GPIO63 (EDGE_BOTH)，極性反轉 |
| 電源控制 | GPIO117 (regulator-fixed，always-on) |

## 相關原始碼位置 (rubikpi-ai/linux)

```
sound/soc/qcom/qcm6490.c                                     ← ASoC machine driver
sound/soc/codecs/es8316.c                                     ← ES8316 codec driver
sound/soc/codecs/es8316.h                                     ← ES8316 register map
arch/arm64/boot/dts/qcom/qcs6490-thundercomm-rubikpi3.dts    ← 頂層 DTS
arch/arm64/boot/dts/qcom/qcs6490-thundercomm-rubikpi3.dtsi   ← 主要配置
```

## 音頻信號路徑

```
【Playback 播放路徑】
ADSP Q6 DSP
  → PRIMARY_MI2S_RX (q6apmbedai)
  → I2S 總線:
      GPIO96 = MCLK (24.576 MHz，永久開啟)
      GPIO97 = BCLK (1.536 MHz)
      GPIO100 = WS (Word Select / LRCLK)
      GPIO98  = DATA0 (音頻資料輸出)
  → ES8316 (I2C 0x11，解碼)
  → 耳機插孔 (Headphone Jack)

【Capture 錄音路徑】
麥克風 (MIC)
  → ES8316 (I2C 0x11，編碼)
  → I2S 總線:
      GPIO99 = DATA1 (音頻資料輸入)
  → PRIMARY_MI2S_TX (q6apmbedai)
  → ADSP Q6 DSP

【HDMI 音頻路徑】
ADSP Q6 DSP → QUATERNARY_MI2S_RX → LT9611 HDMI bridge → HDMI 輸出

【Jack 偵測路徑】
耳機插拔 → GPIO63 中斷 (EDGE_BOTH，極性反轉)
         → ES8316 jack detect → ALSA Jack 事件
```

## 詳細分析文件

- [Kernel&DT/es8316_driver_analysis.md](Kernel&DT/es8316_driver_analysis.md) — ES8316 驅動程式分析
- [Kernel&DT/qcm6490_machine_driver.md](Kernel&DT/qcm6490_machine_driver.md) — QCM6490 機器驅動分析
- [Kernel&DT/device_tree_analysis.md](Kernel&DT/device_tree_analysis.md) — Device Tree 配置分析
https://github.com/rubikpi-ai/WiringRP-Python
https://github.com/rubikpi-ai/WiringRP
https://github.com/rubikpi-ai/WiringRP-Python
https://github.com/qualcomm-linux/meta-qcom
https://github.com/qualcomm-linux/meta-qcom-hwe
https://github.com/qualcomm-linux/kernel
https://github.com/qualcomm-linux/meta-qcom-qim-product-sdk


Qualcomm Linux 文檔：
https://docs.qualcomm.com/doc/80-70018-16/topic/overview.html?product=895724676033554725&facet=Audio&version=1.4

