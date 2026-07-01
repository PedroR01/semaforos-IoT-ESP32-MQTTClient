#ifndef SENSOR_H
#define SENSOR_H

#include <NewPing.h>
#include <TM1637Display.h>

enum class TrafficState {
  RED_IDLE,
  GREEN_ACTIVE,
  STOP_YELLOW,
  STOP_RED
};

class Sensor {
private:
  static constexpr uint16_t MIN_RANGE_CM = 30;
  static constexpr uint16_t MAX_RANGE_CM = 80;
  static constexpr uint8_t INITIAL_GREEN_TIME_SEC = 10;
  static constexpr uint8_t TIME_INCREMENT_SEC = 5;
  static constexpr uint32_t YELLOW_DURATION_MS = 3000;
  static constexpr uint32_t SONAR_INTERVAL_MS = 100;
  static constexpr uint16_t MAX_SONAR_DISTANCE_CM = 200;

  const uint8_t _pinRed;
  const uint8_t _pinYellow;
  const uint8_t _pinGreen;

  NewPing _sonar;
  TM1637Display _display;

  TrafficState _state;
  unsigned long _stateStartMs;
  unsigned long _lastSonarMs;
  unsigned long _greenEndMs;
  int _lastDisplayedSeconds;

  void setLedsOff();
  void setRedOn();
  void setGreenOn();
  void setYellowOn();
  bool isObjectInRange();
  void updateDisplay(int seconds);
  void clearDisplay();
  void transitionToGreen();
  void transitionToRedIdle();
  void transitionToStopYellow();

  void handleRedIdle();
  void handleGreenActive();
  void handleStopYellow();
  void handleStopRed();

public:
  Sensor(uint8_t pinRed, uint8_t pinYellow, uint8_t pinGreen,
         uint8_t pinTrig, uint8_t pinEcho,
         uint8_t pinClk, uint8_t pinDio);
  void begin();
  void update();
  void handleStop();
};

#endif  // !SENSOR_H
