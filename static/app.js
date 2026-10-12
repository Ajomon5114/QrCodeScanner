// ── Popup helpers ──────────────────────────────────────────
function openPopup() {
    document.getElementById('scan-overlay').classList.add('show');
}

function closePopup() {
    document.getElementById('scan-overlay').classList.remove('show');
    // Resume physical scanner focus if SuperAdmin input exists
    const inp = document.getElementById('scanner-input');
    if (inp) inp.focus();
    // Resume camera scanner if active
    if (window._html5Scanner && window._isCameraMode) {
        window._html5Scanner.resume();
    }
}

// Close popup when clicking outside the card
document.getElementById('scan-overlay').addEventListener('click', function(e) {
    if (e.target === this) closePopup();
});

// ── Main scanner logic ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const isSuperUser        = window.IS_SUPERUSER === true;
    const scannerInput       = document.getElementById('scanner-input');
    const alertBox           = document.getElementById('alert-box');
    const statusIndicator    = document.getElementById('status-indicator');
    const statusIndicatorGun = document.getElementById('status-indicator-gun');
    const tabPhysical        = document.getElementById('tab-physical');
    const tabCamera          = document.getElementById('tab-camera');
    const tabGun             = document.getElementById('tab-gun');
    const physicalContainer   = document.getElementById('physical-scanner-container');
    const cameraContainer    = document.getElementById('camera-scanner-container');
    const gunContainer       = document.getElementById('gun-scanner-container');

    let isProcessing = false;

    window._isCameraMode = false; // Barcode Scanner is first/default for all users
    window._html5Scanner = null;

    // Helper: show brief alert message
    function showAlert(msg, isError = true) {
        if (!alertBox) return;
        alertBox.textContent = msg;
        alertBox.className = isError ? 'alert-box alert-error' : 'alert-box';
        alertBox.style.display = 'block';
        clearTimeout(window._alertTimeout);
        window._alertTimeout = setTimeout(() => {
            alertBox.style.display = 'none';
        }, 4000);
    }

    // Keep physical scanner input focused (only in superadmin mode)
    const enforceFocus = () => {
        if (isSuperUser && !window._isCameraMode && document.getElementById('scan-overlay') &&
            !document.getElementById('scan-overlay').classList.contains('show')) {
            if (scannerInput && document.activeElement !== scannerInput) scannerInput.focus();
        }
    };
    if (isSuperUser) {
        setInterval(enforceFocus, 500);
    }

    // Tab: Physical (SuperAdmin only)
    if (tabPhysical) {
        tabPhysical.addEventListener('click', () => {
            window._isCameraMode = false;
            tabPhysical.classList.add('active');
            if (tabCamera) tabCamera.classList.remove('active');
            if (physicalContainer) physicalContainer.style.display = 'block';
            if (cameraContainer) cameraContainer.style.display = 'none';
            if (window._html5Scanner) window._html5Scanner.pause();
            if (scannerInput) scannerInput.focus();
        });
    }

    // Tab: Barcode Gun (Admin only - hardware scanner without manual typing)
    if (tabGun) {
        tabGun.addEventListener('click', () => {
            window._isCameraMode = false;
            tabGun.classList.add('active');
            if (tabCamera) tabCamera.classList.remove('active');
            if (cameraContainer) cameraContainer.style.display = 'none';
            if (gunContainer) gunContainer.style.display = 'block';
            if (window._html5Scanner) window._html5Scanner.pause();
        });
    }

    // Tab: Camera (Common)
    if (tabCamera) {
        tabCamera.addEventListener('click', () => {
            activateCameraTab();
        });
    }

    function activateCameraTab() {
        window._isCameraMode = true;
        tabCamera.classList.add('active');
        if (tabPhysical) tabPhysical.classList.remove('active');
        if (tabGun) tabGun.classList.remove('active');
        if (physicalContainer) physicalContainer.style.display = 'none';
        if (gunContainer) gunContainer.style.display = 'none';
        if (cameraContainer) cameraContainer.style.display = 'block';

        startOrResumeCamera();
    }

    function startOrResumeCamera() {
        if (!window._html5Scanner) {
            if (typeof Html5QrcodeScanner === 'undefined') {
                cameraContainer.innerHTML = '<div id="camera-loading"><i class="fas fa-spinner fa-spin"></i> Loading camera scanner...</div>';
                const script = document.createElement('script');
                script.src = '/static/html5-qrcode.min.js';
                script.onload = () => {
                    cameraContainer.innerHTML = '<div id="reader"></div>';
                    initCameraScanner();
                };
                document.head.appendChild(script);
            } else {
                initCameraScanner();
            }
        } else {
            window._html5Scanner.resume();
        }
    }

    function initCameraScanner() {
        window._html5Scanner = new Html5QrcodeScanner(
            "reader",
            { fps: 10, qrbox: { width: 250, height: 250 }, aspectRatio: 1.0 },
            false
        );
        window._html5Scanner.render(onCameraScanSuccess, () => {});
    }

    async function onCameraScanSuccess(decodedText) {
        if (isProcessing) return;
        if (window._html5Scanner) window._html5Scanner.pause();
        await processScan(decodedText.trim());
    }

    // SuperAdmin manual/physical input listener
    if (scannerInput) {
        scannerInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (isProcessing) return;
                const userId = scannerInput.value.trim();
                if (!userId) return;
                scannerInput.value = '';
                await processScan(userId);
            }
        });
    }

    // Global barcode scanner listener
    // Hardware scanner guns send characters rapidly (< 60ms average interval)
    // Manual slow human typing is BLOCKED for non-superadmins
    let gunBuffer = '';
    let gunTimestamps = [];

    document.addEventListener('keydown', async (e) => {
        // If popup is open, ignore
        if (document.getElementById('scan-overlay')?.classList.contains('show')) return;
        
        // If superadmin is actively typing in scannerInput, let scannerInput handle it
        if (isSuperUser && document.activeElement === scannerInput) return;

        // Ignore modifier / navigation keys
        if (e.key === 'Shift' || e.key === 'Control' || e.key === 'Alt' || e.key === 'Meta' || e.key === 'Tab' || e.key === 'Escape') return;

        const now = Date.now();

        if (e.key === 'Enter') {
            e.preventDefault();
            const scanned = gunBuffer.trim();
            const timestamps = [...gunTimestamps];
            gunBuffer = '';
            gunTimestamps = [];

            if (!scanned) return;

            // Check if input came from a hardware barcode scanner gun (fast) or manual keyboard (slow)
            let isHardwareScan = false;
            if (timestamps.length >= 2) {
                const totalDuration = timestamps[timestamps.length - 1] - timestamps[0];
                const avgInterval = totalDuration / (timestamps.length - 1);
                // Barcode guns typically fire at 5-30ms per character
                if (avgInterval <= 60) {
                    isHardwareScan = true;
                }
            }

            if (isSuperUser || isHardwareScan) {
                if (isProcessing) return;
                await processScan(scanned);
            } else {
                // Non-superadmin manual entry attempt blocked
                showAlert('Manual seat entry is disabled. Please use the camera or barcode scanner gun.');
            }
            return;
        }

        // Buffer incoming character
        if (e.key.length === 1) {
            // Reset buffer if there was a pause (> 200ms) between keystrokes
            if (gunTimestamps.length > 0 && (now - gunTimestamps[gunTimestamps.length - 1]) > 200) {
                gunBuffer = '';
                gunTimestamps = [];
            }
            gunBuffer += e.key;
            gunTimestamps.push(now);
        }
    });

    async function processScan(userId) {
        isProcessing = true;
        updateStatus('scanning');

        try {
            const response = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId })
            });
            const data = await response.json();

            if (response.ok) {
                showSuccessPopup(data.user);
            } else if (response.status === 409) {
                showWarningPopup(data.user || null, 'Already Marked Present Today');
            } else {
                showErrorPopup(data.error || 'User Not Found');
            }
        } catch (err) {
            console.error("Scan Error:", err);
            showErrorPopup('Network Error. Check connection.');
        } finally {
            isProcessing = false;
            updateStatus('ready');
        }
    }

    // ── Popup builders ──────────────────────────────────────
    function showSuccessPopup(user) {
        const popup = document.getElementById('scan-popup');
        popup.className = 'scan-popup success-popup';
        document.getElementById('popup-icon').textContent = '✅';
        document.getElementById('popup-badge').textContent = 'Marked Present';
        document.getElementById('popup-badge').className = 'popup-badge';
        document.getElementById('popup-details').style.display = 'grid';
        document.getElementById('popup-msg').style.display = 'none';
        document.getElementById('popup-avatar').style.display = 'block';

        fillUserDetails(user);
        openPopup();
    }

    function showWarningPopup(user, msg) {
        const popup = document.getElementById('scan-popup');
        popup.className = 'scan-popup warning-popup';
        document.getElementById('popup-icon').textContent = '⚠️';
        document.getElementById('popup-badge').textContent = 'Already Scanned';
        document.getElementById('popup-badge').className = 'popup-badge already';

        if (user) {
            document.getElementById('popup-details').style.display = 'grid';
            document.getElementById('popup-msg').style.display = 'none';
            document.getElementById('popup-avatar').style.display = 'block';
            fillUserDetails(user);
        } else {
            document.getElementById('popup-details').style.display = 'none';
            document.getElementById('popup-avatar').style.display = 'none';
            document.getElementById('popup-name').textContent = '';
            document.getElementById('popup-msg').style.display = 'block';
            document.getElementById('popup-msg').textContent = msg;
        }
        openPopup();
    }

    function showErrorPopup(msg) {
        const popup = document.getElementById('scan-popup');
        popup.className = 'scan-popup error-popup';
        document.getElementById('popup-icon').textContent = '❌';
        document.getElementById('popup-badge').textContent = 'Not Found';
        document.getElementById('popup-badge').className = 'popup-badge notfound';
        document.getElementById('popup-details').style.display = 'none';
        document.getElementById('popup-avatar').style.display = 'none';
        document.getElementById('popup-name').textContent = '';
        document.getElementById('popup-msg').style.display = 'block';
        document.getElementById('popup-msg').textContent = msg;
        openPopup();
    }

    function fillUserDetails(user) {
        const imgId = user.image_name ? user.image_name : `${user.user_id}.jpg`;
        const avatar = document.getElementById('popup-avatar');
        avatar.dataset.retried = '';
        avatar.src = `/static/images/${imgId}`;
        avatar.onerror = function () {
            if (!this.dataset.retried) {
                this.dataset.retried = 'true';
                this.src = `/static/images/${user.user_id}.jpg`;
            } else {
                this.style.display = 'none';
            }
        };

        document.getElementById('popup-name').textContent         = user.name || '-';
        document.getElementById('popup-church').textContent       = user.church || '-';
        document.getElementById('popup-seat').textContent         = user.seat_no || '-';
        document.getElementById('popup-constituency').textContent  = user.constituency || '-';
        
        let categoryDisplay = user.category || '-';
        if (categoryDisplay.toUpperCase() === 'PB') {
            categoryDisplay = 'Presbyters';
        } else if (categoryDisplay.toUpperCase() === 'LP') {
            categoryDisplay = 'Laypersons';
        } else if (categoryDisplay.toUpperCase() === 'DO') {
            categoryDisplay = 'Diocesan Officers';
        } else if (categoryDisplay.toUpperCase() === 'NOM') {
            categoryDisplay = 'Nominee';
        }
        document.getElementById('popup-category').textContent      = categoryDisplay;
    }

    function updateStatus(state) {
        if (statusIndicator) {
            if (state === 'scanning') {
                statusIndicator.textContent = 'Scanning...';
                statusIndicator.className = 'status-indicator status-scanning';
            } else {
                statusIndicator.textContent = 'Ready';
                statusIndicator.className = 'status-indicator status-ready';
            }
        }
        if (statusIndicatorGun) {
            if (state === 'scanning') {
                statusIndicatorGun.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
                statusIndicatorGun.className = 'status-indicator status-scanning';
            } else {
                statusIndicatorGun.innerHTML = '<i class="fas fa-wifi"></i> LISTENING FOR SCANNER GUN';
                statusIndicatorGun.className = 'status-indicator status-ready';
            }
        }
    }
});
