## What is this?
Simple FastAPI and yt-dlp based server that accepts and processes requests for video/VODS/live-streams download.

## How does it work?
In simple words it runs two API end-points:
1. /download - for accepting and further processing download requests.
2. /task_status/{task_id} - to track status of given tasks(id is provided as response from /download).

## Why do I need this?
Well, simply because of those things:
1. By default, yt-dlp can't properly download part of the **ongoing** streams( --download-sections flag doesn't interact that well with YouTube DASH fragmented streams and won't download correct section from given timestamps). To bypass that we use ***simple magic*** to get correct fragment by ourselves and trick yt-dlp into downloading them.
2. The whole idea is to use it together with [custom-made(and half vibe-coded) Tampermonkey JS script](https://github.com/cmd1337/ytdlp-clipping-server/blob/master/docs/tampermonkey_script.user.js) that adds button under the video, which opens simple interface for clipping(name of the clip, start timestamp and end timestamp). There are a dedicated button for each timestamp to get current timing, which works even if rewind feature is disabled for the stream, so you don't need to guess timestamp by yourself.
3. It can run both locally or on remove server, in first case it will just save downloaded clips to specified directory and provide path to it in response visible on the clipping panel. In case of hosting it remotely you can specify server domain, so it will format link to it and provide it as response instead of path(currently you will need to find a way to host files by yourself, by example with Nginx/Caddy or any other HTTP server, but maybe I'll add simple file server later as well as an option).
4. You're tired of running yt-dlp commands by yourself.

## How do I use it?

The whole purpose is to use it in pair with Tampermonkey script that adds clipping GUI on the YouTube video/stream page. So for that you need to install both server(pure Python, Docker, pre-built .exe) and Tampermonkey extension with userscript added. 

Below will be explained how to install Tampermonkey and userscript and then all three ways to install server.

### Tampermonkey extension and script.

1. Install Tampermonkey extension in your browser(available on all browsers, on Vivaldi it's better to use Violentmonkey). 
2. After you've installed you need to allow userscript usage in the extension settings(not the Tampermonkey settings itself, but the ones in the browser extension page). 
3. Open [script link](https://github.com/cmd1337/ytdlp-clipping-server/raw/refs/heads/master/docs/tampermonkey_script.user.js), and it should automatically redirect you to the script installation page where you just need to agree to install.

Then just open any YouTube video/stream, and you will see "✂️ Clipper" button under the player. Clicking it should open the GUI.


### Server

There are three ways to use it, from easiest(on Windows) to hardest(kinda):
1. Pre-built .exe - all packed in pre-built Python interpreter, dependencies and server itself, probably the easiest if you're on Windows.
2. Docker container - basically runs in background, easily deployable on remote server(so you can access it from any PC), needs a little bit of manual configuration within docker-compose.yml file.
3. Pure Python - easier to customize without manually rebuilding Docker image/remaking .exe executable with pyinstaller.

### Pre-built .exe
1. Download the latest .exe file from release page - https://github.com/cmd1337/ytdlp-clipping-server/releases/latest
2. Put it in any directory wherever you want to run.
   * Windows Defender will probably notify you that it's may be not safe to run, it's because it's basically packed up Python and a bunch of scripts, which seems malicious for it, I can't really do anything to prevent this pop-ups, so if afraid to run it you can check source code and then make your own executable from sources with pyinstaller.
3. It will create all mandatory files and directories< and you will see server icon in the system tray, right click on it will show ip(127.0.0.1/localhost) with port and exit button.
4. After that it's ready to use.

### Pure Python:
In that case you need to have Python installed on your system.
To run it do the following:
1. Either clone this repository or download it as ZIP([Code -> Download ZIP](https://github.com/cmd1337/ytdlp-clipping-server/archive/refs/heads/master.zip)) and then unzip it wherever you want to have it to be.
2. Make .env file.
3. Open terminal/cmd/powershell in directory with all files and run ```pip install -r requirements.txt```
4. Run ``` uvicorn main:app --host 0.0.0.0 --port 8000 --reload```
5. After that it's ready to use.

### Docker
In that case you need to have Docker installed on your system, if you don't better google how to do it.
To run it do the following:
1. Create ```docker-compose.yml``` file in the directory where you want to run it.
2. Open that file in any text editor app and copy the following content and save it:
   ```yaml
   services:
     ytdlp-clipping-server:
       image: cmd1337/ytdlp-clipping-server:latest
       build:
         context: .
       env_file:
         - .env
       ports:
         - "8000:8000"
       volumes:
         - ./downloads:/app/downloads
         - ./logs:/app/logs
       restart: unless-stopped
   ```
3. Create ```.env``` file in the same directory.
4. Open that file in any text editor app and copy the following content and save it:
   ```
   AUTH_TOKEN=your_secret_secure_token_here
   ALLOWED_DOMAINS=youtube.com,youtu.be
   DOWNLOAD_DIR=downloads
   SERVER_DOMAIN=
   LOG_FILE=logs/app.log
   VOD_FORMAT=bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b
   VOD_PROXY=
   ```
5. Open terminal/cmd/powershell in that directory and run ```docker-compose up -d```
6. It will automatically pull image, set it up and run. 
7. After that it's ready to use.

### Actual usage

Once you've installed both tampermonkey userscript and server(in any way), then you can start using it!

To do so you simply need to open any YouTube video/stream and click on "✂️ Clipper" button. 

It will show simple GUI, which contains following elements:
* Clip name, which is used for file name of the clip.
* Start time, it's used as starting timestamp of the clip, right next to it is the button that copies current time in the player(even if rewind disabled on stream).
* End time, basically same as start one, but for ending timestamp.
* Download segment button, which sends all necessary data to the server and start polling process for tracking of the task progress.
* Status block on the right, which shows current progress of the current task, once it's done it will show status and description(path to the file/link).
* History button, that shows logs of 20 latest tasks.
* Settings button, which shows script settings, if you're using basic config and run it locally you don't need to change anything except maybe File Name Template. 
  * File name template - used to generate file name. It uses placeholders to grab metadata of the video and combine it to the desired name at the end. You can see all placeholder by clocking question mark button in the top right corner of that window. By default, it uses %channel_name%_%clip_name%, so if you clip moment from channel named "Example Ch." and put "Test" in Clip name field, then it will result in "Example Ch._Test" with extensions at the end, if such file already exists it will add randon set of 8 characters to prevent rewrite.
  * Remote Server URL - change it you host server remotely, then you need to specify either it's IP and port or domain.
  * Authentication Token - same as remote server url, change it if you host it remotely, but in that case you need to change one in .env config, so it matches, otherwise when you try to clip something you will get 401 Unauthorized HTTP response.
  * Download Endpoint and Status Endpoint is basically for manual tweaking if you want to change endpoints in code itself, probably will be added as config in .env later.
  * Polling Interval - how often it check for task completion in milliseconds, default - 3000 ms - every 3 seconds, you can make it lower if you want to.
  * yt-dlp Command Template - yt-dlp command template for local mode(in the left upper corner of the clipping GUI), simply uses placeholders as file name template, useful if you want to use it to copy pre-made command with all data filled in.
  

### .env config

Same as userscript server has some basic settings you can tweak for yourself by editing .env file.
* AUTH_TOKEN - authorization token used for basic authorization within requests, highly recommended to change it if you host it on remote server. Can be any set of characters.
* ALLOWED_DOMAINS - list of allowed domains to process, basically setting that shows which sites it supports, but as for now the whole purpose is to work with YouTube so you don't need to change it ever. Might be removed as whole later.
* DOWNLOAD_DIR - path for clip downloading dir, by default it uses "downloads" folder in the same directory as server, but you can set nested directories or absolute path.
* LOG_FILE - same as DOWNLOAD_DIR but should specify name of the file at the end.
* VOD_FORMAT - format for downloading finished streams/plain videos, uses basic yt-dlp format selection, more about it [here](https://github.com/yt-dlp/yt-dlp#format-selection), default one downloads the best video quality with mp4 container and the best audio with m4a container, if can't find any, then just the best video and audio, otherwise just best.
* VOD_PROXY - proxy to use for downloading, accepts default proxy schemes such as ```http://ip:port``` or ```socks5://user:pass@ip:port```, more about it [here](https://github.com/yt-dlp/yt-dlp#network-options). As for now it should automatically grab system proxy if one is set, but you can specify it manually here. There is also a bug with local(127.0.0.1) proxies from various VPN clients(x-ray, mihomo, sing-core) in Docker setups, will be fixed later, so if you use such one, then just live this one empty, it should work just fine for now. As for now it doesn't support multiple proxies rotation, but will be added later, probably.
