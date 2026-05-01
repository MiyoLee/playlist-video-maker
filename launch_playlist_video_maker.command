#!/bin/zsh

APP_DIR="/Users/miyolee/opencodeWorkspace"
APP_BIN="$APP_DIR/.venv/bin/playlist-video-maker"

if [ ! -x "$APP_BIN" ]; then
  osascript -e 'display alert "Playlist Video Maker" message "실행 파일을 찾을 수 없습니다. 먼저 환경 설치가 필요합니다." as critical'
  exit 1
fi

pkill -f "playlist-video-maker|playlist_video_maker|python.*playlist-video-maker" >/dev/null 2>&1
nohup "$APP_BIN" >/tmp/playlist-video-maker.log 2>&1 &
