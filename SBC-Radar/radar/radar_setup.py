import serial
import time
import binascii

#function describing sending over the cfg to the radar board, with appropriate delays for different lines
def send_cfg(ser, cfg_lines):
    for line in cfg_lines:
        clean = line.strip()
        if clean == "" or clean.startswith("%"):
            continue  # redundancy to ensure no error in sending cfg

        ser.write((clean + "\n").encode())

        if clean == "flushCfg":
            time.sleep(0.05)  # 50 ms
        else:
            time.sleep(0.01)  # 10 ms

        #print("Sent:", clean)

    # After sensorStart
    time.sleep(0.05)

#function describing how to load the cfg from file
def load_cfg(file):
    cfg_lines = []
    with open(file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("%"):
                cfg_lines.append(line)
    return cfg_lines


