import { useEffect, useRef, useState } from "react";
import "./App.css";

const STORAGE_KEY = "fieldproof-captures";

function readSavedCaptures() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function getDeviceDetails() {
  const agent = navigator.userAgentData;
  const platform = agent?.platform || navigator.platform || "Unknown platform";
  const browser = navigator.userAgent || "Browser details unavailable";
  let device = platform;

  if (/iPhone/i.test(browser)) device = "iPhone";
  else if (/iPad/i.test(browser)) device = "iPad";
  else if (/Android/i.test(browser)) device = "Android device";

  return { device, platform, browser };
}

function formatDate(value) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function App() {
  const videoRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [captures, setCaptures] = useState(readSavedCaptures);
  const capturesRef = useRef(captures);
  const [cameraError, setCameraError] = useState("");
  const [locationMessage, setLocationMessage] = useState("");

  useEffect(() => {
    if (videoRef.current && stream) videoRef.current.srcObject = stream;
    return () => stream?.getTracks().forEach((track) => track.stop());
  }, [stream]);

  function persistCaptures(nextCaptures) {
    capturesRef.current = nextCaptures;
    setCaptures(nextCaptures);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextCaptures));
    } catch {
      setCameraError(
        "Local storage is full. Remove older captures to save more.",
      );
    }
  }

  async function startCamera() {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError(
        "Camera access requires a supported browser and a secure connection (HTTPS).",
      );
      return;
    }

    try {
      const cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" } },
      });
      setStream(cameraStream);
    } catch {
      setCameraError(
        "Camera access was unavailable. Check browser permissions and try again.",
      );
    }
  }

  function updateCaptureLocation(captureId) {
    if (!navigator.geolocation) {
      setLocationMessage("Location is not supported by this browser.");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        persistCaptures(
          capturesRef.current.map((capture) =>
            capture.id === captureId
              ? {
                  ...capture,
                  location: {
                    latitude: coords.latitude,
                    longitude: coords.longitude,
                    accuracy: Math.round(coords.accuracy),
                  },
                }
              : capture,
          ),
        );
        setLocationMessage("Location added to this capture.");
      },
      () =>
        setLocationMessage(
          "Location was not shared. You can enable it in browser settings.",
        ),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }

  function capturePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;

    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 1800 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);

    const device = getDeviceDetails();
    const capture = {
      id: crypto.randomUUID(),
      image: canvas.toDataURL("image/jpeg", 0.84),
      capturedAt: new Date().toISOString(),
      location: null,
      ...device,
    };

    persistCaptures([capture, ...capturesRef.current]);
    setLocationMessage("Requesting location permission…");
    updateCaptureLocation(capture.id);
  }

  function deleteCapture(captureId) {
    persistCaptures(
      capturesRef.current.filter((capture) => capture.id !== captureId),
    );
  }

  return (
    <>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Fieldproof home">
          <span className="brand-mark" aria-hidden="true">
            P
          </span>
          <span>PharmaLedger</span>
        </a>
        <div className="topbar-context">
          <span className="live-dot" /> FIELD RECORDS
        </div>
        <div className="storage-note">Saved on this device</div>
      </header>

      <main id="top" className="workspace">
        <section className="intro">
          <div>
            <p className="eyebrow">COMPLIANCE / FIELD EVIDENCE</p>
            <p className="intro-copy">
              Photos are stored with their capture time, location and device
              details.
            </p>
          </div>
          <div className="record-count">
            <strong>{String(captures.length).padStart(2, "0")}</strong>
            <span>
              LOCAL
              <br />
              RECORDS
            </span>
          </div>
        </section>

        <div className="content-grid">
          <section className="capture-column" aria-labelledby="camera-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">NEW RECORD</p>
                <h2 id="camera-heading">Camera</h2>
              </div>
              <span className={`camera-status ${stream ? "is-ready" : ""}`}>
                <i />
                {stream ? "READY" : "NOT CONNECTED"}
              </span>
            </div>

            <div className={`viewfinder ${stream ? "has-video" : ""}`}>
              <video
                ref={videoRef}
                autoPlay
                muted
                playsInline
                aria-label="Live camera preview"
              />
              {!stream && (
                <div className="camera-placeholder">
                  <span className="camera-glyph" aria-hidden="true">
                    <i />
                  </span>
                  <p>Camera preview will appear here</p>
                  <span>Allow camera access when prompted</span>
                </div>
              )}
              {stream && <div className="viewfinder-corner corner-tl" />}
              {stream && <div className="viewfinder-corner corner-tr" />}
              {stream && <div className="viewfinder-corner corner-bl" />}
              {stream && <div className="viewfinder-corner corner-br" />}
              <span className="frame-label">
                LIVE VIEW <b>•</b> REAR CAMERA
              </span>
            </div>

            {cameraError && (
              <p className="inline-message error-message" role="alert">
                {cameraError}
              </p>
            )}
            {locationMessage && (
              <p className="inline-message" role="status">
                {locationMessage}
              </p>
            )}
            <div className="capture-actions">
              {!stream ? (
                <button className="primary-button" onClick={startCamera}>
                  <span className="button-camera" aria-hidden="true" />
                  Start camera
                </button>
              ) : (
                <button className="primary-button" onClick={capturePhoto}>
                  <span className="shutter-icon" aria-hidden="true" />
                  Capture photo
                </button>
              )}
              {stream && (
                <button className="text-button" onClick={() => setStream(null)}>
                  Stop camera
                </button>
              )}
              <span className="capture-hint">Images stay in this browser</span>
            </div>

            <div className="metadata-strip">
              <div
                className="metadata-symbol location-symbol"
                aria-hidden="true"
              />
              <div>
                <strong>Location</strong>
                <span>Added when permission is granted</span>
              </div>
              <div className="metadata-symbol time-symbol" aria-hidden="true">
                ◷
              </div>
              <div>
                <strong>Capture time</strong>
                <span>Recorded automatically</span>
              </div>
            </div>
          </section>

          <section className="records-column" aria-labelledby="records-heading">
            <div className="section-heading records-heading">
              <div>
                <p className="eyebrow">ON THIS DEVICE</p>
                <h2 id="records-heading">Recent captures</h2>
              </div>
              <span className="record-total">
                {captures.length} {captures.length === 1 ? "FILE" : "FILES"}
              </span>
            </div>

            {captures.length === 0 ? (
              <div className="empty-state">
                <div className="empty-mark" aria-hidden="true">
                  +
                </div>
                <strong>No captures yet</strong>
                <p>Your saved field records will appear here.</p>
              </div>
            ) : (
              <div className="capture-list">
                {captures.map((capture) => (
                  <article className="capture-item" key={capture.id}>
                    <img
                      className="capture-thumbnail"
                      src={capture.image}
                      alt="Captured evidence"
                    />
                    <div className="capture-details">
                      <strong>{formatDate(capture.capturedAt)}</strong>
                      <span>
                        {capture.location
                          ? `${capture.location.latitude.toFixed(5)}, ${capture.location.longitude.toFixed(5)} · ±${capture.location.accuracy} m`
                          : "Location unavailable"}
                      </span>
                      <span>
                        {capture.device} · {capture.platform}
                      </span>
                    </div>
                    <button
                      className="delete-button"
                      onClick={() => deleteCapture(capture.id)}
                      aria-label={`Delete capture from ${formatDate(capture.capturedAt)}`}
                      title="Delete capture"
                    >
                      ×
                    </button>
                  </article>
                ))}
              </div>
            )}
            <p className="privacy-note">
              Device and location details depend on browser permissions. Exact
              phone model may not be available.
            </p>
          </section>
        </div>
        <footer className="page-footer">
          <span>FIELDPROOF / EVIDENCE LOG</span>
          <span>PRIVATE BY DEFAULT · STORED LOCALLY</span>
        </footer>
      </main>
    </>
  );
}

export default App;
