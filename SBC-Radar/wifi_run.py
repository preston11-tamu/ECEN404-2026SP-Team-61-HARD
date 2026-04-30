from wifi import publish_alert, heartbeat
import time

class WifiRunner:
	global confidence
	def __init__(self, room, wifi_queue):
		self.room=room
		self.wifi_queue = wifi_queue
		self.running = True #stop flag
	
	def run(self, fall_event):
		
		Heartbeat_Wait=30
		last_heartbeat=0
		
		while self.running:
			current_time=time.time()
			
			if(current_time-last_heartbeat >= Heartbeat_Wait):
				#print("heartbeat")
				heartbeat()
				last_heartbeat=current_time
				
				
			if fall_event.is_set():
				confidence = self.wifi_queue.get()
				publish_alert(self.room, "Fall Detected", confidence)
				fall_event.clear()
				
		#add a delay to prevent situation where too many alerts are sent at same time
		time.sleep(0.1)
			
			
