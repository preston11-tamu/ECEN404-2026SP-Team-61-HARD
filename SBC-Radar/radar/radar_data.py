import serial
import time
import binascii
import struct
from dataclasses import dataclass, field
from typing import List

from radar.parser_mmw_demo import parser_one_mmw_demo_output_packet

MAGIC = b'\x02\x01\x04\x03\x06\x05\x08\x07' #TI magic decoding number that shows start of frame
HEADER_SIZE = 44 #size of header before data
rx_buf=bytearray() #rx buffer

@dataclass
class DetectedObject:
    x: float = 0
    y: float = 0
    velocity: float = 0
    snr: float = 0

@dataclass
class RadarFrame:
    frame_id: int = 0
    num_objects: int = 0
    objects: List[DetectedObject] = field(default_factory=list)

#parsing script from 403, not used in 404
def parse_data(ser):
    buffer = bytearray()
    data = ser.read(4096)   # read raw bytes from radar
    buffer.extend(data)

    parser_result, \
    headerStartIndex,  \
    totalPacketNumBytes, \
    numDetObj,  \
    numTlv,  \
    subFrameNumber,  \
    detectedX_array,  \
    detectedY_array,  \
    detectedZ_array,  \
    detectedV_array,  \
    detectedRange_array,  \
    detectedAzimuth_array,  \
    detectedElevation_array,  \
    detectedSNR_array,  \
    detectedNoise_array = parser_one_mmw_demo_output_packet(buffer, len(buffer))

    if parser_result == 0:
        # slice off the parsed packet
        buffer = buffer[headerStartIndex + totalPacketNumBytes:]
        if numDetObj > 0:
            print("Detected objects:", numDetObj)
            for i in range(numDetObj):
                print(f"obj{i}: x={detectedX_array[i]}, y={detectedY_array[i]}, z={detectedZ_array[i]}, v={detectedV_array[i]}, snr={detectedSNR_array[i]}")

    else:
        print("FRAME FAIL")
        buffer.clear() #clear the buffer if it fails

#parsing script for frame, uses TI parser to get values from the packet
def parse_frame(packet):
	frame = RadarFrame()
	
	parser_result, \
	headerStartIndex,  \
	totalPacketNumBytes, \
	numDetObj,  \
	numTlv,  \
	subFrameNumber,  \
	detectedX_array,  \
	detectedY_array,  \
	detectedZ_array,  \
	detectedV_array,  \
	detectedRange_array,  \
	detectedAzimuth_array,  \
	detectedElevation_array,  \
	detectedSNR_array,  \
	detectedNoise_array = parser_one_mmw_demo_output_packet(packet, len(packet))

	frame.num_objects=numDetObj
	if numDetObj > 0:
		for i in range(numDetObj):
			obj = DetectedObject()
			obj.x=detectedX_array[i]
			obj.y=detectedY_array[i]
			obj.velocity=detectedV_array[i]
			obj.snr=detectedSNR_array[i]
			frame.objects.append(obj)
	
	return frame
			
			


     

#function to just read in the raw data, no parsing or splitting up data       
def read_uart(ser, rx_buf):
	data=ser.read(ser.in_waiting or 1)
	if data:
		rx_buf.extend(data)


#actually split the raw data into frames
def process_rx_buffer(rx_buffer, out_queue):
	while True:
		start = rx_buffer.find(MAGIC)
		if (start < 0):
			return

		if len(rx_buffer) < start + HEADER_SIZE:
			return

		header = rx_buffer[start:start + HEADER_SIZE] #find the header
		header_fields = struct.unpack('<Q9I', header) #unpacks the data from tlv

		packet_len = header_fields[2]
		frame_number = header_fields[4]
		num_tlvs = header_fields[7]

		if len(rx_buffer) < start + packet_len:
			return

		packet = rx_buffer[start:start + packet_len]
		del rx_buffer[:start + packet_len]
		
		frame = parse_frame(packet)
		frame.frame_id=frame_number
		out_queue.put(frame)
		
def read_data(ser, out_queue):
	#take in the uart data and then process it, if the uart doesnt read in a full frame the processing should skip forawrd until the magic word is found and a full frame can be extracted
	read_uart(ser, rx_buf)
	process_rx_buffer(rx_buf, out_queue)

