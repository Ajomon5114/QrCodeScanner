// ── Popup helpers ──────────────────────────────────────────
function openPopup() {
    document.getElementById('scan-overlay').classList.add('show');
}

function closePopup() {
    document.getElementById('scan-overlay').classList.remove('show');
    // Resume physical scanner focus
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
    const scannerInput     = document.getElementById('scanner-input');
    const alertBox         = document.getElementById('alert-box');
    const statusIndicator  = document.getElementById('status-indicator');
    const tabPhysical      = document.getElementById('tab-physical');
    const tabCamera        = document.getElementById('tab-camera');
    const physicalContainer = document.getElementById('physical-scanner-container');
    const cameraContainer  = document.getElementById('camera-scanner-container');

    let isProcessing = false;

    window._isCameraMode = false;
    window._html5Scanner = null;

    // Keep physical scanner input focused
    const enforceFocus = () => {
        if (!window._isCameraMode && document.getElementById('scan-overlay') &&
            !document.getElementById('scan-overlay').classList.contains('show')) {
            if (scannerInput && document.activeElement !== scannerInput) scannerInput.focus();
        }
    };
    setInterval(enforceFocus, 500);

    // Tab: Physical
    tabPhysical.addEventListener('click', () => {
        window._isCameraMode = false;
        tabPhysical.classList.add('active');
        tabCamera.classList.remove('active');
        physicalContainer.style.display = 'block';
        cameraContainer.style.display = 'none';
        if (window._html5Scanner) window._html5Scanner.pause();
        scannerInput.focus();
    });

    // Tab: Camera (lazy load)
    tabCamera.addEventListener('click', () => {
        window._isCameraMode = true;
        tabCamera.classList.add('active');
        tabPhysical.classList.remove('active');
        physicalContainer.style.display = 'none';
        cameraContainer.style.display = 'block';

        if (!window._html5Scanner) {
            if (typeof Html5QrcodeScanner === 'undefined') {
                cameraContainer.innerHTML = '<div id="camera-loading"><i class="fas fa-spinner fa-spin"></i> Loading camera...</div>';
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
    });

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

    // Physical scanner: listen for Enter
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
        avatar.src = `/static/images/delegates/${imgId}`;
        avatar.onerror = function () {
            if (!this.dataset.retried) {
                this.dataset.retried = 'true';
                this.src = `/static/images/delegates/${user.user_id}.jpg`;
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
        }
        document.getElementById('popup-category').textContent      = categoryDisplay;
    }

    function updateStatus(state) {
        if (!statusIndicator) return;
        if (state === 'scanning') {
            statusIndicator.textContent = 'Scanning...';
            statusIndicator.className = 'status-indicator status-scanning';
        } else {
            statusIndicator.textContent = 'Ready';
            statusIndicator.className = 'status-indicator status-ready';
        }
    }
});
