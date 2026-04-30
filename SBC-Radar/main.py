import serial
import time
import binascii
import queue
import threading
import onnxruntime as ort
from collections import deque
from radar.radar_setup import load_cfg, send_cfg
from radar.radar_data import read_uart, read_data, process_rx_buffer
from wifi_run import WifiRunner
from processing import WindowManager
from radar.radar_reader_class import RadarReader
from ml_runner import MLRunner
import joblib
import traceback

def thread_exception_hook(args):
    print(f"[Thread Error] {args.thread.name}: {args.exc_type.__name__}: {args.exc_value}")
    traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)

threading.excepthook = thread_exception_hook

#define the main function
def main():
    #setup the radar ports
    RADAR_DATA_PORT = "/dev/ttyACM1"
    RADAR_CLI_PORT = "/dev/ttyACM0"
    
    RADAR_DATA_BAUD = 921600
    RADAR_CLI_BAUD = 115200
    
    while True:
        try:
            cli = serial.Serial(RADAR_CLI_PORT, RADAR_CLI_BAUD, timeout=0.1)
            radar = serial.Serial(RADAR_DATA_PORT, RADAR_DATA_BAUD, timeout=0.05)
            print("working ports")
            break
        except Exception as e:
            print("port not ready")
            time.sleep(10)

    #read in cfg from file
    cfg_lines = []
    cfg_lines = load_cfg("radar_setup.cfg")
    #for line in cfg_lines:
    #    print (line)
    #setup the radar with cfg
    #print()
    send_cfg(cli, cfg_lines)
    #print()

    #verify that the radar is set up
    respond=cli.read(4096)
    print(respond)
    print()
    time.sleep(5)
    
    params = {
        'fps': 20,
        'window_sec': 20,
        'overlap_sec': 15
    }
    session = ort.InferenceSession('cnn_fall_detection.onnx')
    scaler = joblib.load('scaler.save')
    
    fall_event = threading.Event()
    wifi_queue = queue.Queue()
    
    frame_queue = queue.Queue()
    window_queue = deque(maxlen=params['fps'] * params['window_sec'])

    radar = RadarReader(radar, frame_queue)
    data_in = WindowManager(frame_queue, window_queue, window_sec=params['window_sec'], overlap_sec=params['overlap_sec'])
    ml = MLRunner(window_queue, params['overlap_sec'], session, scaler, wifi_queue)
    wifi = WifiRunner("Room1", wifi_queue)

    threading.Thread(target=radar.run, daemon=True).start()
    threading.Thread(target=data_in.run, daemon=True).start()
    #threading.Thread(target=ml.run, args=(fall_event, True), daemon=True).start()
    threading.Thread(target=wifi.run, args=(fall_event,), daemon=True).start()

    # main keeps running to allow threading to continue constantly
    #i=0
    #fall_event.set()
    while True:
        #print(window_queue)
        #print(i)
        
        time.sleep(params['window_sec'] - params['overlap_sec'])
        ml.run(fall_event, running=True)

        #fall_event.set()


if __name__ == "__main__":
    main()
