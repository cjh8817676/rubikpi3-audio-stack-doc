# ES8316 Codec 驅動程式分析

原始碼路徑：`sound/soc/codecs/es8316.c` / `es8316.h`  
GitHub：https://github.com/rubikpi-ai/linux/blob/main/sound/soc/codecs/es8316.c

---

## 驅動概覽

ES8316 是 Everest Semiconductor（中科大) 生產的高品質音頻 Codec，支援：
- DAC (Digital→Analog)：用於耳機播放 (最高 48kHz，S16/S20/S24_LE)
- ADC (Analog→Digital)：用於麥克風錄音
- 耳機插拔偵測 (Jack Detection)
- 接口：I2C (配置) + I2S (音頻資料)

---

## RubikPi 3 特有修改

相比於 mainline Linux，rubikpi-ai fork 的 es8316.c 增加了以下功能：

### 1. `init-regs` Device Tree 屬性

驅動在 `es8316_i2c_probe()` 中讀取 DT 的 `init-regs` 屬性：

```c
if (!of_property_read_u32_array(dev->of_node, "init-regs", regs, count)) {
    priv->use_init_regs = 1;
    // 儲存 register init 序列
}
```

`init-regs` 格式為三元組陣列 `<reg val delay_ms>`，例如：
```
init-regs = <
    0x00 0x3f 5    /* 重置，等待 5ms */
    0x00 0x00 0    /* 解除重置 */
    0x0c 0xFF 30   /* VMID 啟動，等待 30ms */
    ...
>;
```

### 2. 兩組 Component Driver

根據是否有 `init-regs`，註冊不同的 component driver：

| 情況 | Component Driver | DAPM Routes |
|------|-----------------|-------------|
| 無 init-regs | `soc_component_dev_es8316` | `es8316_dapm_routes[]` |
| 有 init-regs | `soc_component_dev_es8316_init` | `es8316_init_dapm_routes[]` |

`es8316_init_dapm_routes[]` 是針對 RubikPi 硬體優化的路由配置。

### 3. `es8316_pcm_hw_params()` 分支

當 `use_init_regs == 1` 時，hw_params 使用不同的時鐘配置路徑。

---

## 關鍵函式說明

### `es8316_i2c_probe()`
- I2C probe 函式
- 讀取 `init-regs` DT 屬性，設置 `use_init_regs` 旗標
- 根據 `use_init_regs` 選擇 component driver
- 設置 Jack 偵測 IRQ（`IRQF_TRIGGER_HIGH | IRQF_ONESHOT | IRQF_NO_AUTOEN`）

### `es8316_set_dai_sysclk()`
- 設置 MCLK 頻率
- 根據 MCLK 限制可支援的取樣率

### `es8316_pcm_hw_params()`
- 處理取樣率和格式配置
- 支援 8000~48000 Hz，S16/S20/S24_LE 格式

---

## Regmap 配置

```c
static const struct regmap_config es8316_regmap = {
    .reg_bits   = 8,
    .val_bits   = 8,
    .max_register = 0x53,
    .cache_type = REGCACHE_MAPLE,
};
```

---

## 主要寄存器表 (es8316.h)

| 寄存器地址 | 名稱 | 功能 |
|-----------|------|------|
| 0x00 | ES8316_RESET | 軟體重置 |
| 0x01 | ES8316_CLKMGR_CLKSW | 時鐘開關 |
| 0x02 | ES8316_CLKMGR_CLKSEL | 時鐘選擇 |
| 0x03 | ES8316_CLKMGR_ADCDIV1 | ADC 分頻器 1 |
| 0x04 | ES8316_CLKMGR_ADCDIV2 | ADC 分頻器 2 |
| 0x05 | ES8316_CLKMGR_DACDIV1 | DAC 分頻器 1 |
| 0x06 | ES8316_CLKMGR_DACDIV2 | DAC 分頻器 2 |
| 0x09 | ES8316_SERDATA1 | 串行介面格式 |
| 0x0a | ES8316_SERDATA_ADC | ADC 串行格式 |
| 0x0b | ES8316_SERDATA_DAC | DAC 串行格式 |
| 0x0c | ES8316_SYS_VMIDSEL | VMID 電壓選擇 |
| 0x0e | ES8316_SYS_PDN_CTRL1 | 電源控制 1 |
| 0x0f | ES8316_SYS_PDN_CTRL2 | 電源控制 2 |
| 0x13 | ES8316_HPMIX_SEL | HP Mixer 選擇 |
| 0x16 | ES8316_HPMIX_VOL | HP Mixer 音量 |
| 0x17 | ES8316_CPHP_OUTEN | HP 輸出使能 |
| 0x18~0x1a | ES8316_CPHP_PDN1/2 | 充電泵/HP 電源 |
| 0x29~0x2e | ES8316_DAC_SET* | DAC 設置 |
| 0x50~0x53 | ES8316_GPIO_FLAG | GPIO/Jack 旗標 (volatile) |

---

## ES8316 DAI (Digital Audio Interface)

```
名稱:    "ES8316 HiFi"
取樣率:  8000, 11025, 16000, 22050, 32000, 44100, 48000 Hz
格式:    S16_LE, S20_3LE, S24_LE
```

---

## Jack Detection 機制

1. 插入/移除耳機 → GPIO63 (IRQ_TYPE_EDGE_BOTH) 觸發中斷
2. `es8316_irq()` 處理函式被呼叫
3. 讀取 `ES8316_GPIO_FLAG` 寄存器判斷是否插入
4. 因 DT 設置 `everest,jack-detect-inverted = <1>`，極性需翻轉
5. 通知 ALSA SoC framework → userspace 得知 jack 狀態

---

## 注意事項

- **MCLK 必須持續開啟**：機器驅動 (`qcm6490.c`) 在 `qcm6490_mi2s_mclk_init()` 中設置 MCLK，並在第一個串流開啟時啟動，不會因串流關閉而停止。原因是：「ES8316 IC requires MCLK to be constantly on. If MCLK switches on and off as playback starts and stops, it can easily cause POP sound」
