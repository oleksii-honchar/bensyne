LOG_VERBOSE=false
LOG_LEVEL=debug
# APP_CONFIG_PATH intentionally NOT here: dist runs (nx run racochu:start) must
# resolve to the global ~/.config/racochu.yaml. Dev runs get APP_CONFIG_PATH=dev.yaml
# from the start:dev script only.