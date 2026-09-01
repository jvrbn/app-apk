[app]

# Application metadata
title = Customer Visits
package.name = appapk
package.domain = org.example

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.include_patterns = api/*.py,db/*.py,screens/*.py
source.exclude_dirs = tests,bin,.buildozer,.git,__pycache__

version = 0.1.0

# Python dependencies bundled into the APK. `openssl` and `certifi` are needed
# for HTTPS requests, `sqlite3` for the offline queue.
requirements = python3,kivy==2.3.1,requests,urllib3,chardet,idna,certifi,openssl,sqlite3

orientation = portrait
fullscreen = 0

# Network access is required to submit the forms; the app also keeps working
# offline and syncs later, so it checks the connectivity state.
android.permissions = INTERNET,ACCESS_NETWORK_STATE

android.api = 34
android.minapi = 24
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = False

# Cleartext HTTP is disabled by default: use an https:// endpoint.
android.enable_androidx = True

[buildozer]

log_level = 2
warn_on_root = 1
