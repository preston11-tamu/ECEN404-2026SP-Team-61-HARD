from radar.radar_data import read_data

class RadarReader:
	def __init__(self, radar, frame_queue):
		self.radar=radar
		self.frame_queue=frame_queue
		self.running = True #stop flag
	
	def run(self):
		while self.running:
			read_data(self.radar, self.frame_queue)
	
