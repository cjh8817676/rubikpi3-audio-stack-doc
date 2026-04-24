import wave
import audioop

input_file = "Wii_Music(48k).wav"
output_file = "Wii_Music(44.1k).wav"

with wave.open(input_file, "rb") as src:
    params = src.getparams()
    src_rate = src.getframerate()
    n_channels = src.getnchannels()
    sampwidth = src.getsampwidth()
    frames = src.readframes(src.getnframes())

dst_rate = 44100
converted, _ = audioop.ratecv(frames, sampwidth, n_channels, src_rate, dst_rate, None)

with wave.open(output_file, "wb") as dst:
    dst.setnchannels(n_channels)
    dst.setsampwidth(sampwidth)
    dst.setframerate(dst_rate)
    dst.writeframes(converted)

print(f"Done: {src_rate} Hz -> {dst_rate} Hz => {output_file}")
