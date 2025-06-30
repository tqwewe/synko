from time import time

from syncplay.kodi import player, setplaystate
from syncplay.socket import send
from syncplay.util import getrtt, gs, gsi, gsb  # Added gsb import

_cstate = {
    "ping": {
        "latencyCalculation": 0,
        "clientLatencyCalculation": 0.0,
        "clientRtt": 0
    },
    "playstate": {
        "position": 0.0,
        "paused": True
    }
}
seeking = False


def _setping(sping: dict):
    # Just return this to server, it'll handle generation too.
    _cstate["ping"]["latencyCalculation"] = sping["latencyCalculation"]
    # Server will return this and generation will be handled here.
    _cstate["ping"]["clientLatencyCalculation"] = time()
    # Server needs to acknowledge our CLC and send an RTT for us to calculate ours.
    if "clientLatencyCalculation" in sping:
        _cstate["ping"]["clientRtt"] = getrtt(
            sping["clientLatencyCalculation"],
            sping["serverRtt"]
        )


def handle(sstate: dict):
    _setping(sstate["ping"])

    curtime = player.getTime() if player.isPlaying() else 0.0
    _cstate["playstate"]["position"] = 0.0 if curtime < 0 else curtime

    if "ignoringOnTheFly" in sstate:
        iotf = sstate["ignoringOnTheFly"]
        # If server is asking for a change
        if "server" in iotf:
            _cstate["ignoringOnTheFly"] = {
                "server": iotf["server"]
            }
            if sstate["playstate"]["setBy"] != gs("user"):
                setplaystate(sstate["playstate"], _cstate["playstate"])
                # Kodi is slow, help it out (playstate doesn't update fast enough)
                _cstate["playstate"]["paused"] = sstate["playstate"]["paused"]
                _cstate["playstate"]["position"] = sstate["playstate"]["position"]
        # If another client has already requested a change
        elif "client" in sstate["ignoringOnTheFly"]:
            setplaystate(sstate["playstate"], _cstate["playstate"])
            del _cstate["ignoringOnTheFly"]
    # Delete iotf if its not sent by the server and we don't have an iotf
    elif "ignoringOnTheFly" in _cstate and "client" not in _cstate["ignoringOnTheFly"]:
        del _cstate["ignoringOnTheFly"]
    # Don't check for time difference if we are seeking
    elif not seeking:
        # Calculate time difference (positive = we're behind, negative = we're ahead)
        diff = sstate["playstate"]["position"] - _cstate["playstate"]["position"]
        tolerance_ms = float(gsi("tolerance"))
        tolerance_seconds = tolerance_ms / 1000
        
        # Get rewind threshold from settings with fallback
        try:
            rewind_threshold_setting = gs("rewindThreshold")
            rewind_threshold = float(rewind_threshold_setting) if rewind_threshold_setting else 3.0
        except:
            rewind_threshold = 3.0
        
        # Ensure rewind threshold is at least 2x tolerance
        rewind_threshold = max(tolerance_seconds * 2, rewind_threshold)
        
        # Check if rewind is disabled
        try:
            rewind_disabled = gsb("disableRewind")
        except:
            rewind_disabled = False
        
        # Add network latency compensation
        rtt_compensation = _cstate["ping"]["clientRtt"] / 2 if _cstate["ping"]["clientRtt"] > 0 else 0
        effective_tolerance = tolerance_seconds + rtt_compensation
        
        # Only perform sync actions if difference is significant
        if abs(diff) > effective_tolerance:
            # If we're behind by more than tolerance, sync forward
            if diff > effective_tolerance:
                setplaystate(sstate["playstate"], _cstate["playstate"])
            # If we're ahead by more than rewind threshold, sync backward (only if rewind not disabled)
            elif diff < -rewind_threshold and not rewind_disabled:
                setplaystate(sstate["playstate"], _cstate["playstate"])
            # If we're only slightly ahead (between tolerance and rewind threshold), ignore
            # This prevents constant micro-rewinds that cause the annoying behavior

    send({"State": _cstate})


def dispatch(position: float, paused: bool, seeked: bool):
    if "ignoringOnTheFly" in _cstate:
        return

    _cstate["playstate"]["position"] = position
    if seeked:
        _cstate["playstate"]["paused"] = _cstate["playstate"]["paused"]
        _cstate["playstate"]["doSeek"] = seeked
    else:
        _cstate["playstate"]["paused"] = paused

    _cstate["ignoringOnTheFly"] = {"client": 1}

    send({"State": _cstate})

    # Clear this, since state is stored globally
    if seeked:
        del _cstate["playstate"]["doSeek"]