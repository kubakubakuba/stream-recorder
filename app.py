import os
import time
import threading
import subprocess
import signal
import sys
import shutil
from datetime import datetime
from flask import Flask, render_template, jsonify

try:
	import tomllib
	USING_TOMLLIB = True
except ImportError:
	import toml
	USING_TOMLLIB = False

app = Flask(__name__)

CONFIG_FILE = 'config.toml'
COOKIES_FILE_DEFAULT = 'www.youtube.com_cookies.txt'
RECORDING_DIR = 'recordings'
POLL_INTERVAL = 10
YT_DLP_EXEC = shutil.which("yt-dlp")
YT_DLP_ARGS = [	"-f", "bestvideo+bestaudio",
				"--merge-output-format", "mkv",
				"--no-warnings",
				"--retries", "10",
				"--fragment-retries", "10",
				"--no-part"]

active_processes = {}
stream_status = {}

if not os.path.exists(RECORDING_DIR):
	os.makedirs(RECORDING_DIR)

def get_yt_dlp_path():
	if os.path.exists(YT_DLP_EXEC):
		return YT_DLP_EXEC

	return None

YT_DLP_BINARY = get_yt_dlp_path()

YT_DLP_FOUND = False
try:
	subprocess.run([YT_DLP_BINARY, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	YT_DLP_FOUND = True
except FileNotFoundError:
	YT_DLP_FOUND = False

def get_cookie_file():
	if os.path.exists(COOKIES_FILE_DEFAULT): return COOKIES_FILE_DEFAULT

	return None

def load_config():
	try:
		mode = 'rb' if USING_TOMLLIB else 'r'
		with open(CONFIG_FILE, mode) as f:
			if USING_TOMLLIB:
				return tomllib.load(f)
			else:
				return toml.load(f)
	except Exception as e:
		print(f"Error loading config: {e}", file=sys.stderr)
		return {"streams": []}

def start_recording(stream_index, stream_conf):
	now = datetime.now()
	date_str = now.strftime("%Y%m%d")

	start_time_clean = stream_conf['start'].replace(':', '')

	filename = f"{stream_conf['name']}_{date_str}_{start_time_clean}.mkv"
	filepath = os.path.join(RECORDING_DIR, filename)

	env = os.environ.copy()
	extra_paths = [
		"/home/jakub/.deno/bin",
		"/home/jakub/.local/bin",
		"/usr/local/bin",
		"/usr/bin"
	]
	env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + env.get("PATH", "")

	cmd = [
		YT_DLP_BINARY,
		stream_conf['link'],
		"-o", filepath,
	]

	if YT_DLP_ARGS is not None:
		cmd.extend(YT_DLP_ARGS)

	cookie_file = get_cookie_file()
	if cookie_file:
		cmd.extend(["--cookies", cookie_file])

	try:
		proc = subprocess.Popen(
			cmd,
			preexec_fn=os.setsid,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.PIPE,
			text=True,
			env=env
		)
		active_processes[stream_index] = proc

		msg = f'Recording to {filename}'

		stream_status[stream_index] = {'state': 'Recording', 'message': msg}
		print(f"[START] Recording {stream_conf['name']} to {filename}")
	except Exception as e:
		msg = f"Failed to start: {str(e)}"
		print(f"[ERROR] {msg}", file=sys.stderr)
		stream_status[stream_index] = {'state': 'Error', 'message': msg}

def stop_recording(stream_index):
	if stream_index in active_processes:
		proc = active_processes[stream_index]
		try:
			os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
			proc.wait(timeout=5)
		except Exception as e:
			print(f"[ERROR] Stopping process {stream_index}: {e}", file=sys.stderr)
		finally:
			if stream_index in active_processes:
				del active_processes[stream_index]
			if stream_index in stream_status and stream_status[stream_index]['state'] == 'Recording':
				 stream_status[stream_index] = {'state': 'Idle', 'message': 'Stopped by schedule'}

def check_process_health(idx, name):
	if idx not in active_processes:
		return

	proc = active_processes[idx]
	ret_code = proc.poll()

	if ret_code is not None:
		stderr_output = proc.stderr.read() if proc.stderr else "No output captured"
		short_err = stderr_output.strip().split('\n')[-1] if stderr_output else f"Exit code {ret_code}"

		print(f"[DIED] Stream {name} died: {short_err}")
		stream_status[idx] = {'state': 'Crashed', 'message': short_err[:100]}
		del active_processes[idx]

def check_schedule():
	while True:
		config = load_config()
		now = datetime.now()
		current_day = now.strftime("%a")
		current_time_str = now.strftime("%H:%M")
		curr_time_obj = datetime.strptime(current_time_str, "%H:%M").time()

		valid_indices = []

		for idx, stream in enumerate(config.get('streams', [])):
			valid_indices.append(idx)

			check_process_health(idx, stream.get('name'))

			if stream.get('at') != current_day:
				if idx in active_processes:
					stop_recording(idx)
				continue

			try:
				start_obj = datetime.strptime(stream['start'], "%H:%M").time()
				end_obj = datetime.strptime(stream['end'], "%H:%M").time()
			except ValueError:
				stream_status[idx] = {'state': 'Config Error', 'message': 'Invalid Time Format'}
				continue

			should_record = start_obj <= curr_time_obj < end_obj

			if should_record:
				if idx not in active_processes:
					start_recording(idx, stream)
			else:
				if idx in active_processes:
					stop_recording(idx)

		active_indices = list(stream_status.keys())
		for idx in active_indices:
			if idx not in valid_indices:
				del stream_status[idx]

		time.sleep(POLL_INTERVAL)

scheduler = threading.Thread(target=check_schedule, daemon=True)
scheduler.start()

@app.route('/')
def index():
	config = load_config()
	streams_data = []

	now = datetime.now()
	server_time = now.strftime("%A, %Y-%m-%d %H:%M:%S")

	yt_status_text = f"Found at {YT_DLP_BINARY}" if YT_DLP_FOUND else f"NOT FOUND (Checked: {YT_DLP_BINARY})"

	cookie_file = get_cookie_file()
	auth_status = f"Loaded ({cookie_file})" if cookie_file else "Not Found"

	for idx, stream in enumerate(config.get('streams', [])):
		current_status = stream_status.get(idx, {'state': 'Idle', 'message': 'Waiting for schedule'})

		streams_data.append({
			"name": stream.get('name', 'Unknown'),
			"link": stream.get('link', ''),
			"schedule": f"{stream.get('at')} {stream.get('start')} - {stream.get('end')}",
			"state": current_status['state'],
			"message": current_status['message']
		})

	return render_template(
		'index.html',
		streams=streams_data,
		server_time=server_time,
		yt_dlp_status=yt_status_text,
		auth_status=auth_status
	)

@app.route('/status')
def api_status():
	config = load_config()
	streams_data = []

	now = datetime.now()
	server_time = now.strftime("%A, %Y-%m-%d %H:%M:%S")

	for idx, stream in enumerate(config.get('streams', [])):
		current_status = stream_status.get(idx, {'state': 'Idle', 'message': 'Waiting for schedule'})

		streams_data.append({
			"name": stream.get('name', 'Unknown'),
			"link": stream.get('link', ''),
			"schedule": f"{stream.get('at')} {stream.get('start')} - {stream.get('end')}",
			"state": current_status['state'],
			"message": current_status['message']
		})

	return jsonify({
		'streams': streams_data,
		'server_time': server_time
	})

if __name__ == '__main__':
	app.run(host='0.0.0.0', port=5005)
