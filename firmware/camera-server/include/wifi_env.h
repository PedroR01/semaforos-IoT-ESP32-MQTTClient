#ifndef WIFI_ENV_H
#define WIFI_ENV_H

#include "secrets.h"

// ============================================================
//  Enum de entornos disponibles
// ============================================================

enum class WifiEnv {
  LOCAL,
  CODAPLI,
  MOBILE,
  WOKWI
};

struct WifiCredentials {
  const char *ssid;
  const char *password;
};

// ============================================================
//  "Clase" (namespace + función estática) que resuelve
//  las credenciales según el entorno elegido.
//  Al ser todo inline/constexpr no agrega overhead ni
//  duplica símbolos si el header se incluye en varios .cpp
// ============================================================

class WifiConfig {
  public:
    static WifiCredentials get(WifiEnv env) {
      switch (env) {
        case WifiEnv::LOCAL:
          return { WIFI_SSID_LOCAL, WIFI_PASS_LOCAL };
        case WifiEnv::CODAPLI:
          return { WIFI_SSID_CODAPLI, WIFI_PASS_CODAPLI };
        case WifiEnv::MOBILE:
          return { WIFI_SSID_MOBILE, WIFI_PASS_MOBILE };
        case WifiEnv::WOKWI:
        default:
          return { WIFI_SSID_WOKWI, WIFI_PASS_WOKWI };
      }
    }
};

#endif // WIFI_ENV_H