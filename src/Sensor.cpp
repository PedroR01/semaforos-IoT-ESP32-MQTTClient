#include "Sensor.h"
#include <Arduino.h>

Sensor::Sensor(uint8_t pinRed, uint8_t pinYellow, uint8_t pinGreen,
               uint8_t pinTrig, uint8_t pinEcho,
               uint8_t pinClk, uint8_t pinDio)
    : _pinRed(pinRed),
      _pinYellow(pinYellow),
      _pinGreen(pinGreen),
      _sonar(pinTrig, pinEcho, MAX_SONAR_DISTANCE_CM),
      _display(pinClk, pinDio),
      _state(TrafficState::RED_IDLE),
      _stateStartMs(0),
      _lastSonarMs(0),
      _greenEndMs(0),
      _lastDisplayedSeconds(-1) {}

void Sensor::begin() {
  pinMode(_pinRed, OUTPUT);
  pinMode(_pinYellow, OUTPUT);
  pinMode(_pinGreen, OUTPUT);

  _display.setBrightness(7);
  clearDisplay();
  setRedOn();

  _state = TrafficState::RED_IDLE;
  _stateStartMs = millis();
  _lastSonarMs = 0;
}

void Sensor::update() {
  switch (_state) {
    case TrafficState::RED_IDLE:
      handleRedIdle();
      break;
    case TrafficState::GREEN_ACTIVE:
      handleGreenActive();
      break;
    case TrafficState::STOP_YELLOW:
      handleStopYellow();
      break;
    case TrafficState::STOP_RED:
      handleStopRed();
      break;
  }
}

void Sensor::handleStop() {
  transitionToStopYellow();
}

void Sensor::setLedsOff() {
  digitalWrite(_pinRed, LOW);
  digitalWrite(_pinYellow, LOW);
  digitalWrite(_pinGreen, LOW);
}

void Sensor::setRedOn() {
  digitalWrite(_pinRed, HIGH);
  digitalWrite(_pinYellow, LOW);
  digitalWrite(_pinGreen, LOW);
}

void Sensor::setGreenOn() {
  digitalWrite(_pinRed, LOW);
  digitalWrite(_pinYellow, LOW);
  digitalWrite(_pinGreen, HIGH);
}

void Sensor::setYellowOn() {
  digitalWrite(_pinRed, LOW);
  digitalWrite(_pinYellow, HIGH);
  digitalWrite(_pinGreen, LOW);
}

bool Sensor::isObjectInRange() {
  const uint16_t distance = _sonar.ping_cm();
  if (distance == 0) {
    return false;
  }
  return distance >= MIN_RANGE_CM && distance <= MAX_RANGE_CM;
}

void Sensor::updateDisplay(int seconds) {
  if (seconds != _lastDisplayedSeconds) {
    _display.showNumberDec(seconds, true);
    _lastDisplayedSeconds = seconds;
  }
}

void Sensor::clearDisplay() {
  _display.clear();
  _lastDisplayedSeconds = -1;
}

void Sensor::transitionToGreen() {
  setGreenOn();
  _greenEndMs = millis() + (static_cast<unsigned long>(INITIAL_GREEN_TIME_SEC) * 1000UL);
  _lastDisplayedSeconds = -1;
  updateDisplay(INITIAL_GREEN_TIME_SEC);
  _state = TrafficState::GREEN_ACTIVE;
}

void Sensor::transitionToRedIdle() {
  clearDisplay();
  setRedOn();
  _state = TrafficState::RED_IDLE;
  _lastSonarMs = 0;
}

void Sensor::transitionToStopYellow() {
  clearDisplay();
  setYellowOn();
  _state = TrafficState::STOP_YELLOW;
  _stateStartMs = millis();
}

void Sensor::handleRedIdle() {
  const unsigned long now = millis();
  if (now - _lastSonarMs < SONAR_INTERVAL_MS) {
    return;
  }
  _lastSonarMs = now;

  if (isObjectInRange()) {
    transitionToGreen();
  }
}

void Sensor::handleGreenActive() {
  const unsigned long now = millis();

  if (now < _greenEndMs) {
    const int remainingSeconds =
        static_cast<int>((_greenEndMs - now + 999UL) / 1000UL);
    updateDisplay(remainingSeconds);
    return;
  }

  if (isObjectInRange()) {
    _greenEndMs = now + (static_cast<unsigned long>(TIME_INCREMENT_SEC) * 1000UL);
    _lastDisplayedSeconds = -1;
    updateDisplay(TIME_INCREMENT_SEC);
    return;
  }

  transitionToRedIdle();
}

void Sensor::handleStopYellow() {
  if (millis() - _stateStartMs >= YELLOW_DURATION_MS) {
    setRedOn();
    _state = TrafficState::STOP_RED;
  }
}

void Sensor::handleStopRed() {
  // Estado terminal: rojo encendido indefinidamente.
}
