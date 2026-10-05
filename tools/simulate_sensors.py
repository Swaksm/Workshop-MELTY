"""Publie de fausses mesures capteurs sur le broker, pour tester sans ESP32.

Usage :
    python tools/simulate_sensors.py --table table1 --host localhost --pic
"""

import argparse
import json
import random
import time

import paho.mqtt.publish as publish


def mesure_normale() -> dict:
    return {
        "temp": round(random.gauss(23, 0.5), 1),
        "hum": round(random.gauss(50, 2), 1),
        "gas": random.randint(1100, 1300),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default="table1")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--intervalle", type=float, default=5.0)
    parser.add_argument("--pic", action="store_true", help="envoie un pic de gaz au bout de 60 s")
    args = parser.parse_args()

    topic = f"sentinelx/{args.table}/sensors"
    debut = time.time()
    pic_envoye = False

    while True:
        mesure = mesure_normale()
        if args.pic and not pic_envoye and time.time() - debut > 60:
            mesure = {"temp": 23.1, "hum": 50.2, "gas": 3500}
            pic_envoye = True
            print("pic de gaz envoyé")
        publish.single(topic, json.dumps(mesure), hostname=args.host, port=args.port)
        print(mesure)
        time.sleep(args.intervalle)


if __name__ == "__main__":
    main()
