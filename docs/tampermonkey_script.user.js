// ==UserScript==
// @name         YouTube GUI for ytdlp-clipping-server
// @namespace    http://tampermonkey.net/
// @version      3.6
// @description  Silly half vibecoded TS script for interacting with https://github.com/cmd1337/ytdlp-clipping-server
// @author       cmd1337
// @match        https://www.youtube.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setClipboard
// @connect      *
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    // =========================================================================
    // Config and Locales
    // =========================================================================

    const DEFAULTS = {
        serverUrl: 'http://localhost:8000',
        token: 'your_secret_secure_token_here',
        endpointDownload: '/download',
        endpointStatus: '/task_status/%task_id%',
        pollInterval: 3000,
        cmdTemplate: 'yt-dlp --download-sections "*%current_time%-%end_time%" --force-keyframes-at-cuts -o "%file_name%.%(ext)s" "%url%"',
        fileTemplate: '%channel_name%_%clip_name%',
        mode: 'remote',
        ffmpegPostprocessorArgs: ''
    };

    const LABELS = {
        triggerBtn: '✂️ Clipper',
        localMode: 'Local',
        remoteMode: 'Remote',

        clipNameLabel: 'Clip Name:',
        currentTimeLabel: 'Start Time:',
        endTimeLabel: 'End Time:',

        btnActionLocal: 'Copy Command',
        btnActionRemote: 'Download Segment',

        settingsTitle: 'Advanced Settings',
        serverUrlLabel: 'Remote Server URL:',
        tokenLabel: 'Authentication Token:',
        epDownloadLabel: 'Download Endpoint:',
        epStatusLabel: 'Status Endpoint (%task_id%):',
        intervalLabel: 'Polling Interval (ms):',
        cmdTemplateLabel: 'yt-dlp Command Template:',
        fileTemplateLabel: 'File Name Template:',
        ffmpegPostprocessorArgsLabel: 'ffmpeg Postprocessor Args:',
        btnSave: 'Save Config',

        statusLabel: 'Status:',
        descLabel: 'Desc:',
        btnHistory: '📜 History',
        historyTitle: 'Task History Log (Max 20)',
        historyEmpty: 'No tasks tracked in this session yet.',

        statusPolling: 'Processing...',
        statusTimeInvalid: 'Error: invalid time format (HH:MM:SS required)',
        statusCopied: '✔️ Command copied!',
        statusSending: 'Sending packet...',
        statusServerError: 'Server Error: ',
        statusServerUnreachable: 'Server unreachable.'
    };

    const HELP_TEXT = `Available template placeholders:
• %video_name% — video title
• %channel_name% — channel name
• %current_time% — start timestamp
• %end_time% — end timestamp
• %clip_name% — custom clip text
• %file_name% — resolved file template
• %url% — direct video URL`;

    function validateTimeFormat(timeStr) {
        return /^(?:(?:[0-1]?\d|2[0-3]):)?(?:[0-5]?\d):[0-5]\d$/.test(timeStr);
    }

    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return "00:00:00";
        const h = Math.floor(seconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, '0');
        const s = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }

    function getPlayerTime() {
        const player = document.getElementById("movie_player");
        if (player && typeof player.getCurrentTime === "function") return player.getCurrentTime();
        const video = document.querySelector("video");
        return video ? video.currentTime : 0;
    }

    function getLatencyMode() {
        const player = document.getElementById("movie_player");
        if (player && typeof player.getStatsForNerds === "function") {
            const stats = player.getStatsForNerds();
            if (stats && stats.live_mode) {
                const modeStr = stats.live_mode.toLowerCase();
                if (modeStr.includes("ultra low") || modeStr.includes("ultralow")) return "ultralow";
                if (modeStr.includes("low")) return "low";
            }
        }
        return "normal";
    }

    function getYoutubeMetadata(clipName, currentTime, endTime) {
        let videoName = "video", channelName = "channel";
        const titleEl = document.querySelector('h1.ytd-watch-metadata yt-formatted-string');
        if (titleEl) videoName = titleEl.textContent.trim();
        const channelEl = document.querySelector('ytd-video-owner-renderer #channel-name a');
        if (channelEl) channelName = channelEl.textContent.trim();
        const cleanStr = (str) => str.replace(/[\\/:*?"<>|]/g, "_");

        return {
            video_name: cleanStr(videoName),
            channel_name: cleanStr(channelName),
            current_time: currentTime,
            end_time: endTime,
            clip_name: cleanStr(clipName || "clip"),
            url: window.location.href.split('&')[0]
        };
    }

    function processTemplate(template, meta) {
        return template
            .replace(/%video_name%/g, meta.video_name || '')
            .replace(/%channel_name%/g, meta.channel_name || '')
            .replace(/%current_time%/g, meta.current_time || '')
            .replace(/%end_time%/g, meta.end_time || '')
            .replace(/%clip_name%/g, meta.clip_name || '')
            .replace(/%file_name%/g, meta.file_name || '')
            .replace(/%url%/g, meta.url || '');
    }

    function getSettings() {
        return {
            serverUrl: localStorage.getItem('ytdl_server_url') || DEFAULTS.serverUrl,
            token: localStorage.getItem('ytdl_token') || DEFAULTS.token,
            endpointDownload: localStorage.getItem('ytdl_ep_dl') || DEFAULTS.endpointDownload,
            endpointStatus: localStorage.getItem('ytdl_ep_st') || DEFAULTS.endpointStatus,
            pollInterval: parseInt(localStorage.getItem('ytdl_interval')) || DEFAULTS.pollInterval,
            cmdTemplate: localStorage.getItem('ytdl_cmd_template') || DEFAULTS.cmdTemplate,
            fileTemplate: localStorage.getItem('ytdl_file_template') || DEFAULTS.fileTemplate,
            mode: localStorage.getItem('ytdl_working_mode') || DEFAULTS.mode,
            ffmpegPostprocessorArgs: localStorage.getItem('ytdl_ffmpeg_pp_args') || DEFAULTS.ffmpegPostprocessorArgs
        };
    }

    function getTaskHistory() {
        try { return JSON.parse(localStorage.getItem('ytdl_history_log')) || []; } catch(e) { return []; }
    }

    function saveTaskHistory(history) {
        localStorage.setItem('ytdl_history_log', JSON.stringify(history.slice(0, 20)));
    }

    function addTaskToHistory(taskId, link, status, description) {
        const history = getTaskHistory();
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        history.unshift({ task_id: taskId, link, status, description, last_updated: timestamp });
        saveTaskHistory(history);
        renderHistoryList();
    }

    function updateTaskInHistory(taskId, status, description) {
        const history = getTaskHistory();
        const task = history.find(t => t.task_id === taskId);
        if (task) {
            task.status = status;
            task.description = description;
            task.last_updated = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            saveTaskHistory(history);
            renderHistoryList();
        }
    }

    function createInputField({ labelText, value = '', placeholder = '', width = '100%', hasButton = false, buttonText = '🔄' }) {
        const container = document.createElement('div');
        Object.assign(container.style, { display: 'flex', flexDirection: 'column', gap: '4px' });
        const label = document.createElement('label');
        label.textContent = labelText;
        Object.assign(label.style, { fontSize: '11px', color: '#aaa', fontWeight: '500' });
        container.appendChild(label);

        const row = document.createElement('div');
        Object.assign(row.style, { display: 'flex', gap: '4px', alignItems: 'center' });

        const input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.placeholder = placeholder;
        Object.assign(input.style, {
            background: '#272727', color: '#fff', border: '1px solid #444', padding: '0 10px',
            borderRadius: '4px', fontSize: '13px', width: width, boxSizing: 'border-box', height: '34px'
        });
        row.appendChild(input);

        let btn = null;
        if (hasButton) {
            btn = document.createElement('button');
            btn.textContent = buttonText;
            Object.assign(btn.style, {
                background: '#272727', border: '1px solid #444', width: '34px', height: '34px',
                borderRadius: '4px', cursor: 'pointer', color: '#fff', padding: '0',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '13px', flexShrink: '0'
            });
            row.appendChild(btn);
        }
        container.appendChild(row);
        return { container, input, btn };
    }

    // =========================================================================
    // Interface redner, probably to be a little bit polished later
    // =========================================================================

    let mainPanel = null, settingsPanel = null, historyPanel = null;
    let liveStatusText = null, histListContainer = null;

    function displayLiveStatus(status, description) {
        if (!liveStatusText) return;

        // clean-up
        liveStatusText.textContent = '';

        let color = '#ccc';
        if (status === 'processing' || status === 'pending') color = '#ffaa00';
        else if (status === 'completed' || status === 'success') color = '#44ff44';
        else if (status === 'Timeout' || status.toLowerCase().includes('error')) color = '#ff4444';

        const statusTitle = document.createElement('span');
        statusTitle.style.color = color;
        statusTitle.style.fontWeight = 'bold';
        statusTitle.textContent = LABELS.statusLabel + ' ';

        const statusVal = document.createTextNode(status + ' | ');

        const descTitle = document.createElement('span');
        descTitle.style.color = '#aaa';
        descTitle.style.fontWeight = 'bold';
        descTitle.textContent = LABELS.descLabel + ' ';

        const descVal = document.createTextNode(description);

        liveStatusText.appendChild(statusTitle);
        liveStatusText.appendChild(statusVal);
        liveStatusText.appendChild(descTitle);
        liveStatusText.appendChild(descVal);
    }

    function renderHistoryList() {
        if (!histListContainer) return;

        histListContainer.textContent = '';

        const items = getTaskHistory();
        if (items.length === 0) {
            const emptyNotice = document.createElement('div');
            Object.assign(emptyNotice.style, { color: '#666', fontSize: '12px', textAlign: 'center', padding: '15px' });
            emptyNotice.textContent = LABELS.historyEmpty;
            histListContainer.appendChild(emptyNotice);
            return;
        }

        items.forEach(item => {
            const row = document.createElement('div');
            Object.assign(row.style, {
                background: '#1a1a1a', padding: '8px', borderRadius: '4px', border: '1px solid #333',
                fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '3px'
            });

            const line1 = document.createElement('div');
            Object.assign(line1.style, { display: 'flex', justifyContent: 'space-between', color: '#999' });

            const idSpan = document.createElement('span');
            const idStrong = document.createElement('strong');
            idStrong.textContent = 'ID: ';
            idSpan.appendChild(idStrong);
            idSpan.appendChild(document.createTextNode(item.task_id));

            const timeSpan = document.createElement('span');
            timeSpan.style.color = '#555';
            timeSpan.textContent = item.last_updated;

            line1.appendChild(idSpan);
            line1.appendChild(timeSpan);

            const line2 = document.createElement('div');
            Object.assign(line2.style, { textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' });
            const link = document.createElement('a');
            link.href = item.link;
            link.target = '_blank';
            Object.assign(link.style, { color: '#0055ff', textDecoration: 'none' });
            link.textContent = item.link;
            line2.appendChild(link);

            const line3 = document.createElement('div');
            Object.assign(line3.style, { display: 'flex', justifyContent: 'space-between', alignItems: 'center' });

            const statusSpan = document.createElement('span');
            Object.assign(statusSpan.style, { color: '#ffaa00', fontWeight: 'bold' });
            statusSpan.textContent = item.status;

            const descSpan = document.createElement('span');
            Object.assign(descSpan.style, { color: '#bbb', maxWidth: '70%', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' });
            descSpan.textContent = item.description;

            line3.appendChild(statusSpan);
            line3.appendChild(descSpan);

            row.appendChild(line1);
            row.appendChild(line2);
            row.appendChild(line3);

            histListContainer.appendChild(row);
        });
    }

    function buildUI() {
        // clean-up
        const oldMain = document.getElementById('ytdl-native-panel');
        if (oldMain) oldMain.remove();
        const oldSettings = document.getElementById('ytdl-settings-panel');
        if (oldSettings) oldSettings.remove();
        const oldHistory = document.getElementById('ytdl-history-panel');
        if (oldHistory) oldHistory.remove();

        const currentSettings = getSettings();

        //main panel
        mainPanel = document.createElement('div');
        mainPanel.id = 'ytdl-native-panel';
        Object.assign(mainPanel.style, {
            position: 'fixed', bottom: '0', left: '0', width: '100%', zIndex: '99999',
            background: '#0f0f0f', color: '#fff', borderTop: '1px solid #333',
            fontFamily: 'Roboto, Arial, sans-serif', display: 'none', boxSizing: 'border-box',
            padding: '12px 30px', boxShadow: '0 -5px 25px rgba(0,0,0,0.6)'
        });

        const header = document.createElement('div');
        Object.assign(header.style, { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' });

        const toggleWrapper = document.createElement('div');
        Object.assign(toggleWrapper.style, { display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 'bold' });

        const localLabel = document.createElement('span');
        localLabel.textContent = LABELS.localMode;
        localLabel.style.color = currentSettings.mode === 'local' ? '#fff' : '#666';

        const switchBtn = document.createElement('div');
        Object.assign(switchBtn.style, { width: '36px', height: '18px', background: '#333', borderRadius: '9px', position: 'relative', cursor: 'pointer', border: '1px solid #555' });
        const switchCircle = document.createElement('div');
        Object.assign(switchCircle.style, {
            width: '14px', height: '14px', background: '#cc0000', borderRadius: '50%',
            position: 'absolute', top: '1px', left: currentSettings.mode === 'local' ? '2px' : '18px', transition: 'left 0.2s'
        });
        switchBtn.appendChild(switchCircle);

        const remoteLabel = document.createElement('span');
        remoteLabel.textContent = LABELS.remoteMode;
        remoteLabel.style.color = currentSettings.mode === 'remote' ? '#fff' : '#666';
        toggleWrapper.appendChild(localLabel);
        toggleWrapper.appendChild(switchBtn);
        toggleWrapper.appendChild(remoteLabel);

        const headerActions = document.createElement('div');
        Object.assign(headerActions.style, { display: 'flex', gap: '15px', alignItems: 'center' });
        const settingsIcon = document.createElement('button');
        settingsIcon.textContent = '⚙️';
        Object.assign(settingsIcon.style, { background: 'none', border: 'none', color: '#aaa', fontSize: '16px', cursor: 'pointer' });
        const closeBtn = document.createElement('button');
        closeBtn.textContent = '×';
        Object.assign(closeBtn.style, { background: 'none', border: 'none', color: '#aaa', fontSize: '22px', cursor: 'pointer', lineHeight: '1' });
        headerActions.appendChild(settingsIcon);
        headerActions.appendChild(closeBtn);
        header.appendChild(toggleWrapper);
        header.appendChild(headerActions);
        mainPanel.appendChild(header);

        const contentRow = document.createElement('div');
        Object.assign(contentRow.style, { display: 'flex', gap: '15px', alignItems: 'flex-end' });

        const clipGroup = createInputField({ labelText: LABELS.clipNameLabel, placeholder: 'my_clip', width: '160px' });
        const startGroup = createInputField({ labelText: LABELS.currentTimeLabel, value: '00:00:00', width: '90px', hasButton: true });
        const endGroup = createInputField({ labelText: LABELS.endTimeLabel, placeholder: 'HH:MM:SS', width: '90px', hasButton: true });

        const btnAction = document.createElement('button');
        btnAction.textContent = currentSettings.mode === 'local' ? LABELS.btnActionLocal : LABELS.btnActionRemote;
        Object.assign(btnAction.style, {
            background: '#0055ff', color: '#fff', border: 'none', padding: '0 16px',
            borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', height: '34px', fontSize: '13px'
        });

        const statusZone = document.createElement('div');
        Object.assign(statusZone.style, {
            display: 'flex', alignItems: 'center', gap: '12px', marginLeft: 'auto',
            background: '#161616', padding: '0 12px', borderRadius: '4px', border: '1px solid #2b2b2b', height: '34px'
        });
        liveStatusText = document.createElement('span');
        Object.assign(liveStatusText.style, { fontSize: '12px', color: '#ccc', whiteSpace: 'nowrap' });
        statusZone.appendChild(liveStatusText);

        const btnHistory = document.createElement('button');
        btnHistory.textContent = LABELS.btnHistory;
        Object.assign(btnHistory.style, {
            background: '#2a2a2a', border: '1px solid #444', color: '#fff',
            borderRadius: '4px', cursor: 'pointer', padding: '4px 8px', fontSize: '11px', fontWeight: '500'
        });
        statusZone.appendChild(btnHistory);

        contentRow.appendChild(clipGroup.container);
        contentRow.appendChild(startGroup.container);
        contentRow.appendChild(endGroup.container);
        contentRow.appendChild(btnAction);
        contentRow.appendChild(statusZone);
        mainPanel.appendChild(contentRow);
        document.body.appendChild(mainPanel);

        displayLiveStatus('-', '-');

        // settings panel
        settingsPanel = document.createElement('div');
        settingsPanel.id = 'ytdl-settings-panel';
        Object.assign(settingsPanel.style, {
            position: 'fixed', bottom: '75px', right: '30px', zIndex: '100000',
            background: '#212121', border: '1px solid #444', padding: '15px 20px',
            borderRadius: '8px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
            width: '420px', display: 'none', flexDirection: 'column', gap: '10px',
            maxHeight: '75vh', overflowY: 'auto'
        });

        const sHeader = document.createElement('div');
        Object.assign(sHeader.style, { display: 'flex', justifyContent: 'space-between', alignItems: 'center' });
        const sTitle = document.createElement('span');
        sTitle.textContent = LABELS.settingsTitle;
        Object.assign(sTitle.style, { fontSize: '14px', fontWeight: 'bold' });
        const btnHelp = document.createElement('button');
        btnHelp.textContent = '❓';
        Object.assign(btnHelp.style, { background: 'none', border: 'none', cursor: 'pointer' });
        sHeader.appendChild(sTitle);
        sHeader.appendChild(btnHelp);
        settingsPanel.appendChild(sHeader);

        const helpBlock = document.createElement('div');
        helpBlock.textContent = HELP_TEXT;
        Object.assign(helpBlock.style, { background: '#141414', padding: '8px', borderRadius: '4px', fontSize: '11px', color: '#aaa', display: 'none', whiteSpace: 'pre-line' });
        settingsPanel.appendChild(helpBlock);

        const srvField = createInputField({ labelText: LABELS.serverUrlLabel, value: currentSettings.serverUrl });
        const tokField = createInputField({ labelText: LABELS.tokenLabel, value: currentSettings.token, placeholder: 'Optional security token' });
        const dlEpField = createInputField({ labelText: LABELS.epDownloadLabel, value: currentSettings.endpointDownload });
        const stEpField = createInputField({ labelText: LABELS.epStatusLabel, value: currentSettings.endpointStatus });
        const intField = createInputField({ labelText: LABELS.intervalLabel, value: currentSettings.pollInterval.toString() });
        const cmdField = createInputField({ labelText: LABELS.cmdTemplateLabel, value: currentSettings.cmdTemplate });
        const fileField = createInputField({ labelText: LABELS.fileTemplateLabel, value: currentSettings.fileTemplate });
        const ffmpegArgsField = createInputField({labelText: LABELS.ffmpegPostprocessorArgsLabel, value: currentSettings.ffmpegPostprocessorArgs, placeholder: '-vf scale=1280:-2 -c:a copy'});

        const btnSaveSettings = document.createElement('button');
        btnSaveSettings.textContent = LABELS.btnSave;
        Object.assign(btnSaveSettings.style, { background: '#cc0000', color: '#fff', border: 'none', padding: '8px', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer', marginTop: '4px' });

        settingsPanel.appendChild(srvField.container);
        settingsPanel.appendChild(tokField.container);
        settingsPanel.appendChild(dlEpField.container);
        settingsPanel.appendChild(stEpField.container);
        settingsPanel.appendChild(intField.container);
        settingsPanel.appendChild(cmdField.container);
        settingsPanel.appendChild(fileField.container);
        settingsPanel.appendChild(ffmpegArgsField.container);
        settingsPanel.appendChild(btnSaveSettings);
        document.body.appendChild(settingsPanel);

        // history panel, someday will be reworked for sure lmao
        historyPanel = document.createElement('div');
        historyPanel.id = 'ytdl-history-panel';
        Object.assign(historyPanel.style, {
            position: 'fixed', bottom: '75px', right: '30px', zIndex: '100000',
            background: '#212121', border: '1px solid #444', padding: '15px',
            borderRadius: '8px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
            width: '450px', display: 'none', flexDirection: 'column', gap: '10px'
        });
        const hHeader = document.createElement('div');
        Object.assign(hHeader.style, { display: 'flex', justifyContent: 'space-between', alignItems: 'center' });
        const hTitle = document.createElement('span');
        hTitle.textContent = LABELS.historyTitle;
        Object.assign(hTitle.style, { fontSize: '14px', fontWeight: 'bold' });
        const hClose = document.createElement('button');
        hClose.textContent = '×';
        Object.assign(hClose.style, { background: 'none', border: 'none', color: '#aaa', fontSize: '18px', cursor: 'pointer' });
        hHeader.appendChild(hTitle);
        hHeader.appendChild(hClose);
        historyPanel.appendChild(hHeader);

        histListContainer = document.createElement('div');
        Object.assign(histListContainer.style, { overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '300px' });
        historyPanel.appendChild(histListContainer);
        document.body.appendChild(historyPanel);

        // =========================================================================
        // basic(bad) logic
        // =========================================================================

        btnHelp.addEventListener('click', () => helpBlock.style.display = helpBlock.style.display === 'none' ? 'block' : 'none');

        switchBtn.addEventListener('click', () => {
            const settings = getSettings();
            const newMode = settings.mode === 'local' ? 'remote' : 'local';
            localStorage.setItem('ytdl_working_mode', newMode);
            switchCircle.style.left = newMode === 'local' ? '2px' : '18px';
            localLabel.style.color = newMode === 'local' ? '#fff' : '#666';
            remoteLabel.style.color = newMode === 'remote' ? '#fff' : '#666';
            btnAction.textContent = newMode === 'local' ? LABELS.btnActionLocal : LABELS.btnActionRemote;
            displayLiveStatus('-', '-');
        });

        settingsIcon.addEventListener('click', () => {
            if (settingsPanel && historyPanel) {
                settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'flex' : 'none';
                historyPanel.style.display = 'none';
            }
        });

        btnHistory.addEventListener('click', () => {
            if (historyPanel && settingsPanel) {
                const isHidden = historyPanel.style.display === 'none';
                historyPanel.style.display = isHidden ? 'flex' : 'none';
                settingsPanel.style.display = 'none';
                if (isHidden) renderHistoryList();
            }
        });

        hClose.addEventListener('click', () => { if (historyPanel) historyPanel.style.display = 'none'; });

        closeBtn.addEventListener('click', () => {
            if (mainPanel) mainPanel.style.display = 'none';
            if (settingsPanel) settingsPanel.style.display = 'none';
            if (historyPanel) historyPanel.style.display = 'none';
        });

        startGroup.btn.addEventListener('click', () => startGroup.input.value = formatTime(getPlayerTime()));
        endGroup.btn.addEventListener('click', () => endGroup.input.value = formatTime(getPlayerTime()));

        btnSaveSettings.addEventListener('click', () => {
            localStorage.setItem('ytdl_server_url', srvField.input.value.trim());
            localStorage.setItem('ytdl_token', tokField.input.value.trim());
            localStorage.setItem('ytdl_ep_dl', dlEpField.input.value.trim());
            localStorage.setItem('ytdl_ep_st', stEpField.input.value.trim());
            localStorage.setItem('ytdl_interval', intField.input.value.trim());
            localStorage.setItem('ytdl_cmd_template', cmdField.input.value.trim());
            localStorage.setItem('ytdl_file_template', fileField.input.value.trim());
            localStorage.setItem('ytdl_ffmpeg_pp_args', ffmpegArgsField.input.value.trim());
            if (settingsPanel) settingsPanel.style.display = 'none';
        });

        // status polling
        function pollRemoteStatus(taskId, config, retryCount = 0) {
            const urlPath = config.endpointStatus.replace('%task_id%', taskId);
            const fullUrl = `${config.serverUrl.replace(/\/$/, "")}${urlPath}`;

            GM_xmlhttpRequest({
                method: "GET",
                url: fullUrl,
                timeout: 6000,
                onload: function(res) {
                    if (res.status === 200) {
                        try {
                            const data = JSON.parse(res.responseText);
                            const status = data.status || 'unknown';
                            const desc = data.description || '';

                            displayLiveStatus(status, desc);
                            updateTaskInHistory(taskId, status, desc);

                            if (status === "processing" || status === "pending") {
                                setTimeout(() => pollRemoteStatus(taskId, config, 0), config.pollInterval);
                            }
                        } catch(e) {
                            handlePollError(taskId, config, retryCount, "Parse Error");
                        }
                    } else {
                        handlePollError(taskId, config, retryCount, `HTTP ${res.status}`);
                    }
                },
                onerror: () => handlePollError(taskId, config, retryCount, "Network Error"),
                ontimeout: () => handlePollError(taskId, config, retryCount, "Timeout")
            });
        }

        function handlePollError(taskId, config, retryCount, reason) {
            if (retryCount < 3) {
                setTimeout(() => pollRemoteStatus(taskId, config, retryCount + 1), config.pollInterval);
            } else {
                const status = "Timeout";
                const desc = `Failed to connect to server (${reason}) at URL: ${config.serverUrl}`;
                displayLiveStatus(status, desc);
                updateTaskInHistory(taskId, status, desc);
            }
        }

        btnAction.addEventListener('click', () => {
            const startVal = startGroup.input.value.trim();
            const endVal = endGroup.input.value.trim();

            let valid = true;
            if (!validateTimeFormat(startVal)) { startGroup.input.style.borderColor = '#ff4444'; valid = false; } else { startGroup.input.style.borderColor = '#444'; }
            if (!validateTimeFormat(endVal)) { endGroup.input.style.borderColor = '#ff4444'; valid = false; } else { endGroup.input.style.borderColor = '#444'; }
            if (!valid) { displayLiveStatus('Error', LABELS.statusTimeInvalid); return; }

            const activeSettings = getSettings();
            const meta = getYoutubeMetadata(clipGroup.input.value.trim(), startVal, endVal);
            const resolvedFileName = processTemplate(activeSettings.fileTemplate, meta);
            meta.file_name = resolvedFileName;

            if (activeSettings.mode === 'local') {
                const finalCommand = processTemplate(activeSettings.cmdTemplate, meta);
                GM_setClipboard(finalCommand);
                displayLiveStatus('Success', LABELS.statusCopied);
            } else {
                displayLiveStatus('Pending', LABELS.statusSending);
                const targetUrl = `${activeSettings.serverUrl.replace(/\/$/, "")}${activeSettings.endpointDownload}`;

                GM_xmlhttpRequest({
                    method: "POST",
                    url: targetUrl,
                    headers: { "Content-Type": "application/json" },
                    data: JSON.stringify({
                        token: activeSettings.token,
                        link: meta.url,
                        filename: resolvedFileName,
                        start_time: meta.current_time,
                        end_time: meta.end_time,
                        timescale: getLatencyMode(),
                        ffmpeg_postprocessor_args: activeSettings.ffmpegPostprocessorArgs
                    }),
                    onload: function(res) {
                        if (res.status === 200) {
                            try {
                                const data = JSON.parse(res.responseText);
                                const taskId = data.task_id;
                                const initialStatus = data.status || 'pending';
                                const qPos = data.queue_position !== undefined ? data.queue_position : '-';
                                const initialDesc = `Queue Position: ${qPos}`;

                                displayLiveStatus(initialStatus, initialDesc);
                                addTaskToHistory(taskId, meta.url, initialStatus, initialDesc);

                                pollRemoteStatus(taskId, activeSettings, 0);
                            } catch(e) {
                                displayLiveStatus('Error', 'Failed to parse response schema.');
                            }
                        } else {
                            displayLiveStatus('Error', `${LABELS.statusServerError}${res.status}`);
                        }
                    },
                    onerror: () => displayLiveStatus('Error', LABELS.statusServerUnreachable)
                });
            }
        });
    }

    // =========================================================================
    // pretty cool youtube style button!
    // =========================================================================

    function injectNativeButton() {
        const actionsMenu = document.querySelector('#top-row #actions #actions-inner #menu ytd-menu-renderer #top-level-buttons-computed');
        if (!actionsMenu || document.getElementById('ytdl-native-trigger')) return;

        const triggerBtn = document.createElement('button');
        triggerBtn.id = 'ytdl-native-trigger';
        triggerBtn.textContent = LABELS.triggerBtn;
        Object.assign(triggerBtn.style, {
            background: 'rgba(255, 255, 255, 0.1)', color: '#fff', border: 'none',
            padding: '0 16px', borderRadius: '18px', height: '36px',
            fontSize: '13px', fontWeight: '500', cursor: 'pointer', marginLeft: '8px',
            fontFamily: 'Roboto, Arial, sans-serif'
        });

        triggerBtn.addEventListener('mouseenter', () => triggerBtn.style.background = 'rgba(255, 255, 255, 0.2)');
        triggerBtn.addEventListener('mouseleave', () => triggerBtn.style.background = 'rgba(255, 255, 255, 0.1)');

        triggerBtn.addEventListener('click', () => {
            buildUI();

            if (mainPanel) {
                const isHidden = mainPanel.style.display === 'none';
                mainPanel.style.display = isHidden ? 'block' : 'none';
                if (isHidden) {
                    const startInput = mainPanel.querySelector('label + div input');
                    if (startInput) startInput.value = formatTime(getPlayerTime());
                } else {
                    if (settingsPanel) settingsPanel.style.display = 'none';
                    if (historyPanel) historyPanel.style.display = 'none';
                }
            }
        });

        actionsMenu.appendChild(triggerBtn);
    }

    function removeInterface() {
        const oldMain = document.getElementById('ytdl-native-panel');
        if (oldMain) oldMain.remove();
        const oldSettings = document.getElementById('ytdl-settings-panel');
        if (oldSettings) oldSettings.remove();
        const oldHistory = document.getElementById('ytdl-history-panel');
        if (oldHistory) oldHistory.remove();

        const trigger = document.getElementById('ytdl-native-trigger');
        if (trigger) trigger.remove();

        mainPanel = null;
        settingsPanel = null;
        historyPanel = null;
        liveStatusText = null;
        histListContainer = null;
    }

    window.addEventListener('yt-navigate-finish', () => {
        const isVideo = window.location.pathname.startsWith('/watch') || window.location.pathname.startsWith('/live/');
        if (!isVideo) removeInterface(); else setTimeout(injectNativeButton, 1000);
    });

    setInterval(() => {
        const isVideo = window.location.pathname.startsWith('/watch') || window.location.pathname.startsWith('/live/');
        if (isVideo && !document.getElementById('ytdl-native-trigger')) injectNativeButton();
    }, 2000);

})();