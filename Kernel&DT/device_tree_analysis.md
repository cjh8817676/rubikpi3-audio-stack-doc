# Device Tree 配置分析 — RubikPi 3

DTS 文件路徑：
- `arch/arm64/boot/dts/qcom/qcs6490-thundercomm-rubikpi3.dts`
- `arch/arm64/boot/dts/qcom/qcs6490-thundercomm-rubikpi3.dtsi`

GitHub：https://github.com/rubikpi-ai/linux/tree/main/arch/arm64/boot/dts/qcom

---

## 頂層 DTS (`qcs6490-thundercomm-rubikpi3.dts`)

```dts
/dts-v1/;
#include "qcs6490-thundercomm-rubikpi3.dtsi"
/ {
    model = "Thundercomm, Inc. RUBIK Pi 3";
    compatible = "qcom,qcm6490-addons-idp", "qcom,sc7280";
    qcom,msm-id = <497 0x10000>, <498 0x10000>, <475 0x10000>, <515 0x10000>;
    qcom,board-id = <32 0xb>, <32 0x60b>;
};
```

主要配置全在 `.dtsi` 中，頂層只宣告 model 名稱與 SoC ID。

---

## ES8316 Codec 節點

位置：`&i2c0` 節點內

```dts
&i2c0 {
    status = "ok";
    es8316: es8316@11 {
        compatible = "everest,es8316";
        reg = <0x11>;                    /* I2C 地址 = 0x11 */
        clocks = <&q6prmcc LPASS_CLK_ID_MCLK_1 LPASS_CLK_ATTRIBUTE_COUPLE_NO>;
        clock-names = "mclk";
        #sound-dai-cells = <0>;
        dummy-supply = <&es8316_enable_vreg>;
        interrupts-extended = <&tlmm 63 IRQ_TYPE_EDGE_BOTH>;
        everest,jack-detect-inverted = <1>;
        init-regs = < ... >;             /* 40+ 寄存器初始化三元組 */
        status = "ok";
    };
};
```

---

## ES8316 電源控制節點

```dts
/* 在 &soc 節點內 */
es8316_enable_vreg: es8316_enable_vreg {
    compatible = "regulator-fixed";
    regulator-name = "es8316_enable_vreg";
    pinctrl-names = "default";
    pinctrl-0 = <&es8316_power_on>;
    gpio = <&tlmm 117 GPIO_ACTIVE_HIGH>;
    enable-active-high;
    regulator-always-on;   /* 永久開啟！ */
};

/* 在 &tlmm 節點內 */
es8316_power_on: es8316_power_on {
    pins = "gpio117";
    function = "gpio";
    drive-strength = <2>;
    bias-pull-down;
};
```

- GPIO117 控制 ES8316 電源
- `regulator-always-on`：系統啟動後永久供電

---

## PRIMARY MI2S GPIO 腳位

| GPIO | 信號名稱 | 功能 |
|------|---------|------|
| GPIO96 | mi2s0_mclk | Master Clock (24.576 MHz，永久開啟) |
| GPIO97 | mi2s0_sclk | Bit Clock (1.536 MHz，串流期間開啟) |
| GPIO98 | mi2s0_data0 | 音頻資料輸出 (Playback) |
| GPIO99 | mi2s0_data1 | 音頻資料輸入 (Capture) |
| GPIO100 | mi2s0_ws | Word Select / LRCLK |

---

## ES8316 init-regs 初始化序列解析

格式：`<寄存器地址  寫入值  延遲毫秒>`

```dts
init-regs = <
    0x00 0x3f 5      /* RESET: 啟動全部重置，等待 5ms */
    0x00 0x00 0      /* RESET: 解除重置 */
    0x0c 0xFF 30     /* SYS_VMIDSEL: 啟動 VMID 基準電壓，等待 30ms */

    /* 時鐘設置 */
    0x02 0x09 0      /* CLKMGR_CLKSEL */
    0x03 0x20 0      /* CLKMGR_ADCDIV1 */
    0x04 0x11 0      /* CLKMGR_ADCDIV2 */
    0x05 0x00 0      /* CLKMGR_DACDIV1 */
    0x06 0x11 0      /* CLKMGR_DACDIV2 */
    0x07 0x00 0      /* CLKMGR reg 0x07 */
    0x08 0x00 0      /* CLKMGR reg 0x08 */

    /* 串行介面格式 */
    0x09 0x04 0      /* SERDATA1: I2S format */
    0x0a 0x0C 0      /* SERDATA_ADC: 24-bit I2S */
    0x0b 0x0C 0      /* SERDATA_DAC: 24-bit I2S */

    /* 系統電源控制 */
    0x10 0x10 0      /* SYS ref */
    0x0e 0x3F 0      /* SYS_PDN_CTRL1: 選擇性電源管理 */
    0x0f 0x1F 0      /* SYS_PDN_CTRL2: 選擇性電源管理 */

    /* HP Mixer / 路由設置 */
    0x13 0x00 0      /* HPMIX_SEL */
    0x14 0x00 0      /* HPMIX_SWITCH */
    0x15 0x00 0      /* HPMIX_PDN */

    /* 充電泵 / 耳機驅動器 */
    0x18 0x11 0      /* CPHP_ICAL_VOL */
    0x17 0x00 0      /* CPHP_OUTEN: HP 輸出初始關閉 */
    0x1b 0x03 0      /* CPHP_PDN1 */
    0x1a 0x22 0      /* CPHP_PDN2 */
    0x19 0x06 0      /* CPHP_PDN3 */
    0x16 0x00 0      /* HPMIX_VOL */

    /* ADC/DAC 設置 */
    0x24 0x01 0      /* ADC_VOLUME */
    0x25 0x08 0      /* ADC_MUTE */
    0x29 0xCD 0      /* DAC_SET1 */
    0x2a 0x08 0      /* DAC_SET2 */
    0x2b 0xA0 0      /* DAC_SET3 */
    0x2c 0x05 0      /* DAC_SET4 */
    0x2d 0x06 0      /* DAC_SET5 */
    0x2e 0xAB 0      /* DAC_ROUTE */

    /* ADC 增益/EQ */
    0x22 0xC0 0      /* ADC_PDN_LINSEL */
    0x1e 0x90 0      /* ADCCONTROL1 */
    0x1f 0x90 0      /* ADCCONTROL2 */
    0x1c 0x0F 0      /* ADCCONTROL3 */
    0x23 0x60 0      /* ADC_EQ_CTRL */

    /* GPIO 設置 */
    0x4d 0x00 0
    0x4e 0x02 0
    0x50 0xA0 0
    0x51 0x00 0
    0x52 0x00 0

    /* 其他寄存器 */
    0x24 0x00 0
    0x27 0x00 0
    0x31 0x00 0
    0x33 0x00 0
    0x34 0x00 0
    0x2f 0x00 0
>;
```

---

## Sound Card 節點

```dts
sound: sound {
    compatible = "qcom,qcm6490-sndcard";
    model = "qcm6490-idp-snd-card";

    /* PRIMARY MI2S → ES8316 耳機/麥克風 */
    mi2s-playback-dai-link {
        link-name = "MI2S-LPAIF-RX-PRIMARY";
        cpu   { sound-dai = <&q6apmbedai PRIMARY_MI2S_RX>; };
        codec { sound-dai = <&msm_stub_codec 0>, <&es8316>; };
    };
    mi2s-capture-dai-link {
        link-name = "MI2S-LPAIF-TX-PRIMARY";
        cpu   { sound-dai = <&q6apmbedai PRIMARY_MI2S_TX>; };
        codec { sound-dai = <&msm_stub_codec 1>, <&es8316>; };
    };

    /* QUATERNARY MI2S → LT9611 HDMI bridge */
    quaternary-mi2s-playback-dai-link {
        link-name = "MI2S-LPAIF_RXTX-RX-PRIMARY";
        cpu   { sound-dai = <&q6apmbedai QUATERNARY_MI2S_RX>; };
        codec { sound-dai = <&msm_stub_codec 0>, <&lt9611_codec>; };
    };

    /* TDM, QUINARY MI2S, TERTIARY MI2S links ... */
};
```

---

## 已停用的音頻子系統

RubikPi 3 不使用 Qualcomm 內建的 WCD codec，以下全部停用：

```dts
&lpass_rx_macro  { status = "disabled"; }
&lpass_tx_macro  { status = "disabled"; }
&lpass_wsa_macro { status = "disabled"; }
&lpass_va_macro  { status = "disabled"; }
&swr0            { status = "disabled"; }   /* SoundWire bus 0 */
&swr1            { status = "disabled"; }   /* SoundWire bus 1 */
&swr2            { status = "disabled"; }   /* SoundWire bus 2 */
```

這表示：
- 無 WCD9380/WCD9385 等內部 codec
- 無 WSA883x 揚聲器放大器
- 音頻路徑完全依賴外部 ES8316

---

## LT9611 HDMI Bridge 配置

```dts
/* i2c9, 地址 0x39 */
lt9611: lt9611@39 {
    compatible = "lontium,lt9611uxc";
    reg = <0x39>;
    interrupts-extended = <&tlmm 20 IRQ_TYPE_EDGE_FALLING>;
    reset-gpios = <&tlmm 21 GPIO_ACTIVE_HIGH>;
    enable-gpios = <&tlmm 83 GPIO_ACTIVE_HIGH>;
    /* LPASS LPI I2S1 (QUATERNARY MI2S) 腳位：
       GPIO6=CLK, GPIO7=WS, GPIO8=DATA, GPIO9=DATA */
};
```

---

## 最近修改

最後一次 commit 標題：**「Asoc: codec: es8316: fix the issue of no sound from headphones」**  
Commit hash: `b1864ac`  
修改文件：`qcs6490-thundercomm-rubikpi3.dtsi`  
說明：更新 ES8316 `init-regs` 序列以修復耳機無聲問題。
