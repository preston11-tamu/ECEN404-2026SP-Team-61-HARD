import preprocessing as pp
import joblib
import tracemalloc
import onnxruntime as ort
import time
import subprocess 
import sys
import numpy as np
import os
import threading

class MLRunner:
	def __init__(self, window_queue, overlap, session, scaler, wifi_queue):
		self.window_queue = window_queue
		self.overlap = overlap
		self.session = session
		self.scaler = scaler
		self.wifi_queue= wifi_queue

	def run(self, fall_event, running):
		if running:
			prediction, confidence = inference(self.window_queue, self.overlap, self.session, self.scaler)
			if (prediction == "FALL"):
				self.wifi_queue.put(confidence)
				fall_event.set()

def inference(window_queue, overlap, ort_session, scaler):
    if (len(window_queue) < 20*overlap):
        time.sleep(0.01)
        return None, None
	
    raw_features = pp.dataprep_queue(window_queue)
    feature_array = np.array(raw_features, dtype=np.float64)
    
    scaled = scaler.transform(feature_array)

    input_sequence = scaled.astype(np.float32)[np.newaxis, :, :]  # Add batch dimension
    lengths = input_sequence.shape[1]
    max_len = np.array([lengths], dtype=np.int64)
    
    threshold = 0.5
    
    try:
    	output_logit = ort_session.run(
        	None,
        	{
            	'sequence': input_sequence,
            	'length': max_len
        	}
    	)

    	logit = output_logit[0][0][0]
    	probability = 1 / (1 + np.exp(-logit))  # Sigmoid
    
    	if probability >= threshold: confidence = np.emath.logn(2.56, probability + 0.6) + 0.5
    	else: confidence = -np.emath.logn(25/9, probability + 0.6) + 0.5
    	confidence *= 100;

    	prediction = "FALL" if probability >= threshold else "NOT FALL"
    	print( "Time: %d-%d-%d  %d:%d:%d\n" % (time.localtime().tm_mon, time.localtime().tm_mday, time.localtime().tm_year, time.localtime().tm_hour, time.localtime().tm_min, time.localtime().tm_sec) )
    	print(f"{os.path.basename('Prediction')}: {prediction} \n({probability:.3f}) ({logit:.3f}) \n({confidence:.2f}% confidence) \n")
    except Exception as e:
        print(f"Error in inferencing: ", e)

    return prediction, confidence

