import time
import grovepi
import RPi.GPIO as gpio
import math
import picamera
import tweepy
import subprocess
import logging
from threading import Timer

#Twitter-Anmeldedaten aus Datei "auth.py" importieren:
from auth import (
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret
        )

#Instagram-Anmeldedaten aus Datei importieren:
from instaauth import (
        username,
        password
        )


################################## EINSTELLUNGEN ###################################################
## können verändert werden, um das Programm an die Bedürfnisse verschiedener Pflanzen anzupassen ###
####################################################################################################

SETTINGS = {
        "TIME_CHECK_LIGHT": 61,      # Lichtcheck-Zeit (Sekunden)
        "TIME_CHECK_TEMP": 62,       # Temperaturcheck-Zeit (Sekunden)
        "TIME_CHECK_WATER": 63,      # Wassercheck-Zeit (Sekunden
        "TIME_PIC": 2*60*59,         # Zeit für Foto/Instagram-Post (Sekunden) (2*60*60 = 2 Stunden)
        "TIME_TWITTER": 60*58,       # Twitterzeit (Sekunden) (1*60*60 = 1 Stunde)
        "LIGHT_FROM": 8,             # Anfangszeit Licht (Stunde)
        "LIGHT_UNTIL": 20,           # Endzeit Licht (Stunde)
        "LIGHT_THRESHOLD":350,       # Grenzwert, ab dem Licht an geht
        "TEMP_THRESHOLD": 18,        # Temperatur Grenzwert, ab dem Tür auf geht
        "MOISTURE_THRESHOLD": 400,   # Grenzwert, ab dem Wasser gepumpt wird
        "WATERING_TIME": 1.5,        # Zeit, die die Pumpe läuft (Sekunden)
        }

################################## ANSCHLÜSSE ######################################################
## können angepasst werden, falls andere Anschlüsse verwendet werden ###############################

moisture_sensor = 2             #Feuchtigkeitssensor: A2
light_sensor = 1                #Lichtsensor: A1
temp_humidity_sensor = 2        #Temp./Luftf.-Sensor: D2
water_relay = 7                 #Wasserpumpe-Relais: D7
light_relay = 4                 #Licht-Relais auf Port D4
servopin = 17                   #Servomotor an GPIO17 (+ Stromquelle und Masse)


################################## SETUP ###########################################################
## die GrovePi Anschlüsse, Kamera werden vorbereitet und eingestellt. ##############################
## Es wird ein Objekt mit den Anmeldedaten für Tweepy erstellt######################################

#GrovePi-Ports als Output festlegen
grovepi.pinMode(water_relay,"OUTPUT")
grovepi.pinMode(light_relay, "OUTPUT")

#GrovePi-Outputs auf "0" setzen
grovepi.digitalWrite(water_relay,0)
grovepi.digitalWrite(light_relay,1)

#Servomotor: Anschlüsse definieren
gpio.setmode(gpio.BCM)
gpio.setup(servopin, gpio.OUT)
servo = gpio.PWM(servopin, 50)

#Kamera-Vorbereitung
camera = picamera.PiCamera()

#Twitter-Anmeldung (Tweepy)
auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
apitweepy = tweepy.API(auth)



################################## FUNKTIONEN DEFINIEREN ###########################################
####################################################################################################

## Sensoren auslesen
def read_sensor():
        try:
                moisture = grovepi.analogRead(moisture_sensor)
                time.sleep(0.3)
                light = grovepi.analogRead(light_sensor)
                time.sleep(0.3)
                [temp,hum] = grovepi.dht(temp_humidity_sensor,0)
                if math.isnan(temp) or math.isnan(hum): # falls Messfehler
                        return [-1,-1,-1,-1]
                return [moisture,light,temp,hum]

        except IOError as TypeError:
                        return [-1,-1,-1,-1]


## Sensordaten in String konvertieren
def read_sensor_readable():
        readings = [moisture,light,temp,hum] = read_sensor()
        if -1 in readings:
            return "Leider stehen momentan keine Messwerte zur Verfügung."
        else:
            output = "Water: " + str(moisture) + "\nLight: " + str(light) + "\nTemperature: " + str(temp) + "\nHumidity: " + str(hum)
            return output


## Licht an/aus
def light_on(state=True):
    """
    Input: True (anschalten) oder False (ausschalten) (bool)
    Relais der LED wird an- bzw. ausgeschaltet
    """
        if state == True:
                grovepi.digitalWrite(light_relay,0)
        else:
                grovepi.digitalWrite(light_relay,1)


## Tür öffnen/schließen
def open_door(winkel):
    """
    Input: Winkel (int/flt)
    Servomotor wird geöffnet/geschlossen.
    """
        if winkel < 0:
                winkel = 0
        if winkel > 180:
                winkel = 180
        servowinkel = winkel / 20.0 + 2.5
        servo.start(servowinkel)
        time.sleep(2)
        servo.ChangeDutyCycle(0)


## Licht-Check
def check_light():
    """
    Überprüft, ob es hell genug ist. Wenn nicht, wird die LED-Leiste angeschaltet.
    Falls es Nacht ist (entsprechend der in SETTINGS eingestellten Uhrzeit) wird nicht überprüft.
    """
        logging.info("Check light...")
        stunde = time.strftime("%H")

        if SETTINGS["LIGHT_FROM"] <= int(stunde) <= SETTINGS["LIGHT_UNTIL"]:
                lvalue = read_sensor()[1]
                if lvalue <= SETTINGS["LIGHT_THRESHOLD"] and lvalue != -1:
                        light_on()
                        print(lvalue)
                        print("Licht an, weil zu dunkel")
                elif lvalue == -1:
                        print(lvalue)
                        print("Sensorfehler. Licht an/aus gelassen.")
                else:
                        light_on(False)
                        print(lvalue)
                        print("Licht aus, weil hell genug")
        else:
                light_on(False)
                print("Licht aus, weil Nacht.")


## Wasser-Check
def check_water():
    """
    Überprüft, ob die Erde feucht genug ist.
    Wenn zu trocken, wird die Pumpe angeschaltet (so lange wie in SETTINGS festgelegt).
    """
        logging.info("Check water...")
        mvalue = read_sensor()[0]
        if mvalue < SETTINGS["MOISTURE_THRESHOLD"] and mvalue != -1:
                print(mvalue)
                print("Wasser!")
                grovepi.digitalWrite(water_relay,1)
                time.sleep(SETTINGS["WATERING_TIME"])
                grovepi.digitalWrite(water_relay,0)

        elif mvalue == -1:
                print(mvalue)
                print("Sensorfehler. Kein Wasser gegeben.")

        elif mvalue >= SETTINGS["MOISTURE_THRESHOLD"]:
                print(mvalue)
                print("Erde ist feucht genug!")

        else:
                print(mvalue)
                print("Sensorfehler. Kein Wasser gegeben.")


## Temperatur-Check
def check_temp():
    """
    überprüft, ob die gemessenen Temperaturwerte in Ordnung sind. Wenn zu hoch, wird die Luke geöffnet
    """
        logging.info("Check temperature...")
        tvalue = read_sensor()[2]
        if tvalue > SETTINGS["TEMP_THRESHOLD"] and tvalue != -1:
                open_door(90) # Winkel 90 = offen
                print(tvalue)
                print("Fenster offen!")

        elif tvalue <= SETTINGS["TEMP_THRESHOLD"]:
                print(tvalue)
                open_door(0) # Winkel 0 = geschlossen
                print("Fenster geschlossen!")

        elif tvalue == -1:
                print(tvalue)
                print("Sensorfehler. Fenster offen/geschlossen gelassen.")

        else:
                print("Fehler: Temperaturcheck")




################################## KOMMUNIKATION ###################################################
####################################################################################################

## Twitter
def twitterpost():
    """
    postet die vom Sensor gemessenen Werte auf Twitter
    """
        datetime_t = str(time.strftime("%d.%m.%Y - %H:%M"))
        status = datetime_t + ":" + "\n" + str(read_sensor_readable())
        apitweepy.update_status(status = status)
        print(status + " getwittert!")


## Foto machen & auf Instagram hochladen
def instapost():
    """
    nimmt mithilfe der Picam ein Foto auf und postet es (mit Datum & Uhrzeit) auf Instagram
    """
        datetime_i = str(time.strftime("%d-%m-%Y_%H-%M"))
        picturename = "Pflanze_" + datetime_i + ".jpg"
        light_on(True)
        time.sleep(2)
        camera.resolution = (768, 768)
        camera.start_preview()
        camera.annotate_text = str(time.strftime("%d.%m.%Y\n%H:%M"))
        camera.capture("/home/pi/Schreibtisch/RasPiPlant/Fotos/" + picturename) #Auf den richtigen Pfad anpassen!
        camera.stop_preview()
        stunde = time.strftime("%H")
        if SETTINGS["LIGHT_FROM"] <= int(stunde) <= SETTINGS["LIGHT_UNTIL"]:
                lvalue = read_sensor()[1]
                if lvalue > SETTINGS["LIGHT_THRESHOLD"]:
                        light_on(False)
        else:
                light_on(False)
        print("Foto aufgenommen")
        time.sleep(1)
        #Instapy über Console aufrufen:
        fotopath = "/home/pi/Schreibtisch/RasPiPlant/Fotos/" + picturename #Auf den richtigen Pfad anpassen!
        caption = datetime_i #nur ein Wort!
        subprocess.Popen("instapy -u " + username + " -p " + password + " -f " + fotopath + " -t " + caption, shell=True)
        print("Instagram Post!")



################################## FUNKTIONEN AUFRUFEN #############################################
####################################################################################################
## Einmal am Anfang ablaufen lassen, um nicht warten zu müssen:
time.sleep(5)
check_light()
time.sleep(2)
check_temp()
time.sleep(2)
check_water()
time.sleep(2)
twitterpost()
time.sleep(2)
instapost()


################################## HAUPTSCHLEIFE ###################################################
####################################################################################################

def schedule_timing(interval, callback):
        timer = Timer(interval, callback)
        timer.start()
        return timer

try:
        t1 = schedule_timing(SETTINGS["TIME_CHECK_LIGHT"], check_light)
        t2 = schedule_timing(SETTINGS["TIME_CHECK_TEMP"], check_temp)
        t3 = schedule_timing(SETTINGS["TIME_CHECK_WATER"], check_water)
        t4 = schedule_timing(SETTINGS["TIME_TWITTER"], twitterpost)
        t5 = schedule_timing(SETTINGS["TIME_PIC"], instapost)

        while True:
                if t1.finished.is_set():
                        t1 = schedule_timing(SETTINGS["TIME_CHECK_LIGHT"], check_light)
                if t2.finished.is_set():
                        t2 = schedule_timing(SETTINGS["TIME_CHECK_TEMP"], check_temp)
                if t3.finished.is_set():
                        t3 = schedule_timing(SETTINGS["TIME_CHECK_WATER"], check_water)
                if t4.finished.is_set():
                        t4 = schedule_timing(SETTINGS["TIME_TWITTER"], twitterpost)
                if t5.finished.is_set():
                        t5 = schedule_timing(SETTINGS["TIME_PIC"], instapost)

except KeyboardInterrupt:
        print("Programm unterbrochen.")

except:
        print("Es ist ein Fehler aufgetreten.")

## Den GPIO-Pin wieder in den Ausgangszustand zurücksetzen:
finally:
        gpio.cleanup()
