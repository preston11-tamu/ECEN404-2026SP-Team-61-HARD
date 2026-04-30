from collections import deque

#define a sliding window that uses deque to pop and append continuosly
class WindowManager:
	def __init__(self, in_queue, out_queue,
                 fps=20, window_sec=8, overlap_sec=4):
		self.in_queue = in_queue
		self.out_queue = out_queue
		self.window_frames = fps * window_sec
		self.step_frames = fps * (window_sec - overlap_sec)
		self.buffer = deque(maxlen=self.window_frames)

	def run(self):
		while True:
			frame = self.in_queue.get()
			self.buffer.append(frame)
			
			#once we reach the correct number of frames we need to pop it out as a list to be read by ML
			if len(self.buffer) == self.window_frames:
				#if (frame!=previoustail+60):
				#	print(previoustail)
				#	print(frame)
				#	print("no good")
				window = list(self.buffer)
				self.out_queue.extend(window)
				for _ in range(self.step_frames):
					self.buffer.popleft()
