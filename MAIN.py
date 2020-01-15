import os 
import argparse
import face_recognition
import cv2 
import numpy as np 
import tkinter as tk
import time
import pickle 
import matplotlib.pyplot as plt
import l293d.driver as l293d
from imutils.video import VideoStream
from imutils.video import FPS
from imutils import paths
from prettytable import PrettyTable
from PIL import Image 
import RPI.GPIO as GPIO

#GPIO.setmode(GPIO.BOARD)
#GPIO.setup(16, GPIO.IN)
#GPIO.setup(12, GPIO.IN)
#camera = PiCamera()
#rawCapture = PiRGBArray(camera)
#time.sleep(0.1)


### Baseline functions which create list of employees & preliminary log based on status of office
def image_path():
  """ 
  returns path to folder of images
  """
  BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # os.path.dirname returns directory name of path to file
  image_dir = os.path.join(BASE_DIR, "images") # path to folder inside GenOne called "images"
  return image_dir

def get_employees():
  """
  Returns list of all employees permitted in office based on provided images
  Baseline state = all are out of office
  """
  label_ids = []
  for dirpath, dirnames, files in os.walk(image_path()): # generates tuple w/ filenames
    for file in files: # look through each image in folder
      if file.endswith("png") or file.endswith("jpg"): # if file found is viable image...
        name = os.path.basename(dirpath).replace(" ", "_").lower() # gives back folder name
        if name not in label_ids:
          label_ids.append(name)

  return label_ids 

def id_dict():
  current_id = 0
  label_ids = {}
  names = get_employees()
  for name in names:
    label_ids[name] = current_id
    current_id += 1
  return label_ids
  
def default_log():
  """
  Returns dictionary logging all employees out of office
  """
  emp_lis = get_employees() # log of employees w/ id numbers
  def_log = {} # new dic for table entries

  for val in emp_lis:
    name = val.replace("_", " ")
    def_log[name] = "out of office"

  return def_log


### Check for states of lock and door; control servomotor to change lock state if door is closed
def lock_state():
  """
  Tells RPI whether deadbolt is in locked or unlocked position
  unlocked = True
  locked = False
  """
  if GPIO.input(16) == 1:
    return True
  else:
    return False
  GPIO.cleanup()

def door_state():
  """
  Reads whether door is open or closed based on info from limit switches
  open = True
  closed = False
  """
  if GPIO.input(16)==1:
    return True
  else:
    return False
  GPIO.cleanup()

def unlock():
  """
  Given info from lock_state(), controls servomotor and unlock deadbolt
  """
  motor = l293d.motor(0,0,0) # input pins the motor uses
  for i in range(0,90): # change 150 to fit needs
    motor.counterclockwise()
  l293d.cleanup()

def lock():
  """
  Given info from lock_state(), controls servomotor and lock deadbolt
  """
  motor = l293d.motor(0,0,0) # input pins the motor uses
  for i in range(0,90): # change 150 to fit needs
    motor.clockwise()
  l293d.cleanup()


### Facial detection foundational controls
def faces_train():

  """
  Using faces function, looks at detected faces and tries to recognize/classify them
  returns boolean regarding if face is recognized
  """
  args = {'dataset': '/Users/anna/Desktop/deep-learning/dataset', 'encodings': '/Users/anna/Desktop/deep-learning/encodings.pickle', 'detection_method': 'cnn'}

  # grab the paths to the input images in our dataset
  print("[INFO] quantifying faces...")
  imagePaths = list(paths.list_images(args["dataset"]))
  knownEncodings = []
  knownNames = []

  for (i, imagePath) in enumerate(imagePaths): # loop over each image in dataset
    
    print("[INFO] processing image {}/{}".format(i + 1, len(imagePaths)))
    name = imagePath.split(os.path.sep)[-2] # extract the person name from the image path
    image = cv2.imread(imagePath)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) 	# convert input image from RGB (OpenCV ordering)
    boxes = face_recognition.face_locations(rgb, model = args["detection_method"]) 	# detect coordinates of box around face in image
    encodings = face_recognition.face_encodings(rgb, boxes) # compute the facial embedding for the face

    for encoding in encodings:
      # add each encoding + name to our set of known names and
      knownEncodings.append(encoding)
      knownNames.append(name)

  # dump the facial encodings + names to disk
  print("[INFO] serializing encodings...")
  data = {"encodings": knownEncodings, "names": knownNames}
  f = open(args["encodings"], "wb")
  f.write(pickle.dumps(data))
  f.close()

### Camera state controls
def cam_initialize():
  vs = VideoStream(usePiCamera=True).start()
  time.sleep(2.0)

def hall_camera():
  """
  Takes in video footage from hallway cam and uses facial detection to distinguish people
  """
  args = {'cascade': '/Users/anna/Desktop/deep-learning/haarcascade_frontalface_default.xml', 'encodings': '/Users/anna/Desktop/deep-learning/encodings.pickle'}

  # load the known faces & embeddings along with OpenCV's Haarcascade for face detection
  data = pickle.loads(open(args["encodings"], "rb").read())
  detector = cv2.CascadeClassifier(args["cascade"])

  while True:
    frame = VideoStream(usePiCamera=True).read()
    roi_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi_color = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    faces = detector.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30), flags=cv2.CASCADE_SCALE_IMAGE)

    # box coordinates in (x, y, w, h), need (top, right, bottom, left) order --> reorder
    boxes = [(y, x + w, y + h, x) for (x, y, w, h) in faces]
    encodings = face_recognition.face_encodings(roi_color, boxes) 	# compute  facial embeddings for each face bounding box

    for face in encodings:
      matches = face_recognition.compare_faces(data["encodings"], face) # attempt to match each face in the input image to encodings
      name = "Unknown"
      if True in matches:
        matchedIdxs = [i for (i, b) in enumerate(matches) if b]
        counts = {}
        for i in matchedIdxs:
          name = data["names"][i]
          counts[name] = counts.get(name, 0) + 1
        name = max(counts, key=counts.get) # determine recognized face w/ most votes

    if name != "Unknown":
      return name

def office_camera():
  """
  Takes in video footage from inside camera and uses facial detection to detect people
  """
  args = {'cascade': '/Users/anna/Desktop/deep-learning/haarcascade_frontalface_default.xml', 'encodings': '/Users/anna/Desktop/deep-learning/encodings.pickle'}

  # load the known faces & embeddings along with OpenCV's Haarcascade for face detection
  data = pickle.loads(open(args["encodings"], "rb").read())
  detector = cv2.CascadeClassifier(args["cascade"])

  while True:
    frame = VideoStream(usePiCamera=True).read()
    roi_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi_color = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    faces = detector.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30), flags=cv2.CASCADE_SCALE_IMAGE)

    # box coordinates in (x, y, w, h), need (top, right, bottom, left) order --> reorder
    boxes = [(y, x + w, y + h, x) for (x, y, w, h) in faces]
    encodings = face_recognition.face_encodings(roi_color, boxes) # compute facial embeddings for each face bounding box

    for face in encodings:
      matches = face_recognition.compare_faces(data["encodings"], face) # attempt to match each face in the input image to encodings
      name = "Unknown"

      if True in matches:
        matchedIdxs = [i for (i, b) in enumerate(matches) if b]
        counts = {}
        for i in matchedIdxs:
          name = data["names"][i]
          counts[name] = counts.get(name, 0) + 1
        name = max(counts, key=counts.get) # determine recognized face w/ most votes
        name_COPY = name

      for ((top, right, bottom, left), name) in zip(boxes, name): # loop over the recognized faces
        if abs(right - left) >= 200:
          is_leaving = True
        else:
          is_leaving = False

    if name_COPY != "Unknown":
      return (name_COPY, is_leaving)


### Throughout day, log updates; at end of day, functions detect last employee leaving and final lock
def build_table():
  entry_log = updating_log()
  log_keys = list(entry_log.keys())
  log_vals = list(entry_log.values())

  t = PrettyTable(['Employee', 'Status'])
  for i in range(len(entry_log)):
    t.add_row([log_keys[i],log_vals[i]])
  return t

def lights():
  """
  Detects whether or not last person has turned off the lights before leaving
  Returns True if lights are off
  """
  camera.capture(rawCapture, format="rgb")
  iamge = rawCapture.array
  black_thresh = 75 # 0 = pitch black, 255 = bright white
  if image < black_thresh:
    return True
  else:
    return False


#########################
# turn on RPI
# start server
# initialize main code?
#########################

faces_train()
cam_initialize()
log_main = default_log()

while(True):

  # check door state
  if door_state(): # open
    if not lock_state(): # locked
      unlock()
  if not door_state(): # closed
    if log_main == default_log():
      lock()

  # check outside camera
  if hall_camera() != None: # if camera detects a recognized face
    name = hall_camera()
    if not door_state():
      if not lock_state():
        unlock()
    log_main[name] = "in office"

  # check entry log
  if log_main != default_log():
    if lights(): # dark
      time.sleep(30)
      lock()
      log_main = default_log()
    if not lights(): # lights on
      if office_camera() != None: # detects face
        if office_camera()[1]:
          unlock()
          log_main[office_camera()[0]] = "out of office"