import collections
import os
import re
import time
from threading import Thread

from loguru import logger

import cv2
import numpy as np
from watchdog.events import PatternMatchingEventHandler

from .segscanner import Scanner

Bounds = collections.namedtuple("Bounds", ['top', 'bottom', 'left', 'right'])


class RaidScan:
    @staticmethod
    def process(filename, args, db_wrapper, hash, raidno, captureTime, captureLat, captureLng, src_path, radius):
        logger.debug("Cropscanning started")
        scanner = Scanner(args, db_wrapper, hash)
        logger.info("Initialized scanned, starting analysis of {}", str(filename))
        checkcrop = scanner.start_detect(filename, hash, raidno, captureTime, captureLat, captureLng, src_path, radius)
        return checkcrop


class checkScreenshot(PatternMatchingEventHandler):
    def __init__(self, args, db_wrapper):
        super().__init__()
        self.args = args
        self.db_wrapper = db_wrapper
        logger.debug("Starting fileobserver...")
        if args.ocr_multitask:
            logger.info("Using proccesses")
            from multiprocessing import Pool
            self.thread_pool = Pool(processes=args.ocr_thread_count)
        else:
            logger.info("Using threads")
            from multiprocessing.pool import ThreadPool
            self.thread_pool = ThreadPool(processes=args.ocr_thread_count)
        logger.info("Starting pogo window manager in OCR thread")

        # let's start a thread handling the tasks...

    def cropImage(self, screenshot, captureTime, captureLat, captureLng, src_path):
        p = None
        raidNo = 0
        processes = []

        hash = str(time.time())
        orgScreen = screenshot
        height, width, channel = screenshot.shape
        gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7, 7), 2)

        minRadius = int(((width / 4.736)) / 2)
        maxRadius = int(((width / 4.736)) / 2)
        logger.debug('Searching for Raid Circles with Radius from {} to {} px', str(minRadius), str(maxRadius))

        circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, 20, param1=50, param2=30, minRadius=minRadius, maxRadius=maxRadius)

        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            for (x, y, r) in circles:
                logger.debug('Found Circle with x:{}, y:{}, r:{}', str(x), str(y), str(r))
                raidNo += 1
                raidCropFilepath = os.path.join(self.args.temp_path, str(hash) + "_raidcrop" + str(raidNo) + ".jpg")
                new_crop = orgScreen[y-r-int((r*2*0.03)):y+r+int((r*2*0.75)), x-r-int((r*2*0.03)):x+r+int((r*2*0.3))]
                cv2.imwrite(raidCropFilepath, new_crop)
                logger.info("Starting processing of crop")
                self.thread_pool.apply_async(RaidScan.process, args=(raidCropFilepath, self.args, self.db_wrapper,
                                                                     hash, raidNo,
                                                                     captureTime, captureLat, captureLng, src_path, r))
                # asyncTask.get()
                # if args.ocr_multitask:
                #     p = multiprocessing.Process(target=RaidScan.process, name='OCR-crop-analysis-' + str(raidNo),
                #                                 args=(self.args, raidCropFilepath, hash, raidNo, captureTime,
                #                                       captureLat, captureLng, src_path, r))
                # else:
                #   p = Thread(target=RaidScan.process, name='OCR-processing', args=(self.args, raidCropFilepath, hash,
                #                                                                      raidNo, captureTime, captureLat,
                #                                                                      captureLng, src_path, r))
                # processes.append(p)
                # p.daemon = True
                # p.start()

    def process(self, event):
        # pathSplit = event.src_path.split("/")
        # filename = pathSplit[len(pathSplit) - 1]
        # print filename
        time.sleep(2)
        # groups: 1 -> timestamp, 2 -> latitude, 3 -> longitude, 4 -> raidcount
        raidcount = re.search(r'.*raidscreen_(\d+\.?\d*)_(-?\d+\.?\d+)_(-?\d+\.?\d+)_(\d+)(\.jpg|\.png).*', event.src_path)
        if raidcount is None:
            # we could not read the raidcount... stop
            logger.warning("Could not read raidcount in {}", event.src_path)
            return
        captureTime = (raidcount.group(1))
        captureLat = (raidcount.group(2))
        captureLng = (raidcount.group(3))
        amountOfRaids = int(raidcount.group(4))

        logger.debug("Capture time {} of new file", str(captureTime))
        logger.debug("Read a lat of {} in new file", str(captureLat))
        logger.debug("Read a lng of {} in new file", str(captureLng))
        logger.debug("Read a raidcount of {} in new file", str(amountOfRaids))
        raidPic = cv2.imread(event.src_path)
        if raidPic is None:
            logger.warning("FileObserver: Image passed is None, aborting.")
            return
        # amountOfRaids = self.pogoWindowManager.getAmountOfRaids(event.src_path)
        if amountOfRaids is None or amountOfRaids == 0:
            return
        processes = []
        bounds = []

        self.cropImage(raidPic, captureTime, captureLat, captureLng, event.src_path)
        logger.debug("process: Done starting off processes")

    patterns = ['*.png', '*.jpg']
    ignore_directories = True
    ignore_patterns = ""
    case_sensitive = False

    def on_created(self, event):
        t = Thread(target=self.process(event), name='OCR-processing')
        t.daemon = True
        t.start()
        # TODO: code this better....
