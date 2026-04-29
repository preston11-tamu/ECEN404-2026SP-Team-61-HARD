import os, sys, getopt
import pickle, json
from demo_structs import Demo_session
from common_structs import Executor
import glob


demo_command_path = 'demo_config.cfg'

command_baud_rate = 115200
data_baud_rate = 921600
max_buffer_size = 2**30 #1 Gigabyte

#Get CLI arguments
opts, _ =  getopt.getopt(sys.argv[1:], "", ["command_port=", "data_port=", "duration=" ,
                                            "visualizer_data_loc=", "pickle_data_loc="
                                            "indent_json", "data_type=", "field_op="])
opts = {item[0].replace("--", ""):item[1] for item in opts}

executor_args = {
                    "command_port":opts["command_port"],
                    "data_port":opts["data_port"],
                    "command_baud_rate":command_baud_rate,
                    "data_baud_rate":data_baud_rate,
                    "commands":None,
                    "session_class":Demo_session
                }
executor = Executor(**executor_args)

if "visualizer_data_loc" in opts:
    with open(opts["visualizer_data_loc"], "rb") as f:
        bin_str = f.read()
    with open("tmp_raw.pickle", "wb") as f:
        pickle.dump(bin_str, f)

    executor.load_raw_data("tmp_raw.pickle")
    executor.parse()
    executor.set_dir("simulation", timestamp_subdir=False)
    executor.save_parsed_data(index=0)

elif "data_type" in opts:
    if opts["data_type"] == 'fall':
        datasize = len([f for f in os.listdir('raw_data/fall/') if os.path.isfile(os.path.join('raw_data/fall/', f))])
        for num in range(1,datasize+1):
            with open(f"raw_data/fall/raw ({num}).dat", "rb") as f:
                bin_str = f.read()
            with open("tmp_raw.pickle", "wb") as f:
                pickle.dump(bin_str, f)

            executor.load_raw_data("tmp_raw.pickle")
            executor.parse()
            executor.set_dir("data/fall", timestamp_subdir=False)
            executor.save_parsed_data(index=num)

    elif opts["data_type"] == 'notfall':
        datasize = len([f for f in os.listdir('raw_data/not_fall/') if os.path.isfile(os.path.join('raw_data/not_fall/', f))])
        for num in range(1,datasize+1):
            with open(f"raw_data/not_fall/raw ({num}).dat", "rb") as f:
                bin_str = f.read()
            with open("tmp_raw.pickle", "wb") as f:
                pickle.dump(bin_str, f)

            executor.load_raw_data("tmp_raw.pickle")
            executor.parse()
            executor.set_dir("data/not_fall", timestamp_subdir=False)
            executor.save_parsed_data(index=num)
    
    elif opts["data_type"] == 'test':
        for f in glob.glob(os.path.join('simulation/', '*.dat')):
            with open(f, "rb") as file:
                bin_str = file.read()
            with open("tmp_raw.pickle", "wb") as file:
                pickle.dump(bin_str, file)

            executor.load_raw_data("tmp_raw.pickle")
            executor.parse()
            executor.set_dir("simulation", timestamp_subdir=False)
            executor.save_parsed_data(index=0,test=True,name=f)
    
    elif opts["data_type"] == 'other':
        for f in glob.glob(os.path.join('raw_data/example_data/', '*.dat')):
            with open(f, "rb") as file:
                bin_str = file.read()
            with open("tmp_raw.pickle", "wb") as file:
                pickle.dump(bin_str, file)

            executor.load_raw_data("tmp_raw.pickle")
            executor.parse()
            executor.set_dir("data/example_data", timestamp_subdir=False)
            executor.save_parsed_data(index=0,test=True,name=f)

elif "field_op" in opts:
    if opts['field_op'] == 'True':
        executor.print_fields()
        


