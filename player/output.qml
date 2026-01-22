import QtQuick
import QtQuick.Controls
import QtMultimedia
import QtQuick.Window

Item {
    id: root
    anchors.fill: parent
    
    // Properties to communicate with Python
    property string currentUrl: ""
    property string currentType: "image"
    property string nextUrl: ""
    property string nextType: "image"
    property bool activeIsA: true
    property bool isFading: false
    property bool nextReady: false
    property int fadeMs: 800
    property int imageDurationMs: 10000
    property int nextDurationMs: 10000
    property string currentScrollMode: "static"
    property string nextScrollMode: "static"
    
    // Signals
    signal mediaFinished(string url, string type)
    signal mediaInfo(string msg)
    signal transitionStarted()
    signal transitionFinished()

    property int videoPosition: activeIsA ? playerA.position : playerB.position
    property int videoDuration: activeIsA ? playerA.duration : playerB.duration

    // Helper function to format time
    function fmt(ms) {
        var s = Math.floor(ms / 1000)
        var m = Math.floor(s / 60)
        var ss = s % 60
        var mm = m < 10 ? ("0" + m) : ("" + m)
        var sss = ss < 10 ? ("0" + ss) : ("" + ss)
        return mm + ":" + sss
    }

    // Prepare the next media in the inactive buffer
    function prepareNext(url, type, duration, textColor, bgColor, textSize, scrollMode) {
        root.mediaInfo("Preparing next: " + url + " (" + type + ")")
        root.nextUrl = url
        root.nextType = type
        root.nextReady = true
        root.nextScrollMode = scrollMode || "static"
        
        var targetItem = root.activeIsA ? bItem : aItem
        var targetPlayer = root.activeIsA ? playerB : playerA
        var targetImage = root.activeIsA ? imageB : imageA
        var targetVideo = root.activeIsA ? videoB : videoA
        var targetText = root.activeIsA ? textB : textA
        var targetBg = root.activeIsA ? bgB : bgA
        
        // Reset state
        targetItem.opacity = 0.0
        targetItem.scale = 1.1
        targetItem.z = 0
        
        // Set colors and text props
        if (textColor && textColor !== "") {
            targetText.color = textColor
        } else {
            targetText.color = "white"
        }
        
        if (bgColor && bgColor !== "") {
            targetBg.color = bgColor
        } else {
            targetBg.color = "black"
        }
        
        if (textSize && textSize > 0) {
            targetText.font.pixelSize = textSize
        } else {
            targetText.font.pixelSize = 80
        }
        
        // Configure Scroll Mode
        targetText.state = root.nextScrollMode
        
        // Set duration for image/text
        if (duration > 0) {
             root.nextDurationMs = duration
        } else {
             root.nextDurationMs = 10000
        }

        if (type === "image") {
            targetPlayer.stop()
            targetImage.source = url
            targetImage.visible = true
            targetVideo.visible = false
            targetText.visible = false
        } else if (type === "text") {
            targetPlayer.stop()
            targetText.text = url
            targetText.visible = true
            targetImage.visible = false
            targetVideo.visible = false
        } else {
            targetImage.visible = false
            targetVideo.visible = true
            targetText.visible = false
            targetPlayer.stop()
            targetPlayer.source = url
            targetPlayer.audioOutput.volume = 0.0
            targetPlayer.play() // Preload/buffer
            // Pause immediately after buffering? 
            // QtMultimedia doesn't have explicit "load", play() starts it.
            // We'll let it play silently or pause when buffered.
        }

        // --- SAFETY CHECK: If current video is already finished, start fade immediately ---
        // This handles cases where a video finishes while we were preparing the next item,
        // or if the video was very short.
        if (root.currentType === "video" && !root.isFading) {
            var currentPlayer = root.activeIsA ? playerA : playerB
            if (currentPlayer.mediaStatus === MediaPlayer.EndOfMedia) {
                root.mediaInfo("Current video finished during prepareNext, forcing fade.")
                startFade()
            }
        }
    }
    
    // Force immediate play (for first item)
    function forcePlay(url, type, duration, textColor, bgColor, textSize, scrollMode) {
        root.mediaInfo("Force playing: " + url)
        root.currentUrl = url
        root.currentType = type
        root.activeIsA = true
        root.nextReady = false
        root.isFading = false
        root.currentScrollMode = scrollMode || "static"
        
        // Set duration
        if (duration > 0) {
             root.imageDurationMs = duration
        } else {
             root.imageDurationMs = 10000
        }
        
        // Set colors for A (since we force A to be active)
        if (textColor && textColor !== "") {
            textA.color = textColor
        } else {
            textA.color = "white"
        }
        
        if (bgColor && bgColor !== "") {
            bgA.color = bgColor
        } else {
            bgA.color = "black"
        }
        
        if (textSize && textSize > 0) {
            textA.font.pixelSize = textSize
        } else {
            textA.font.pixelSize = 80
        }
        
        // Set State
        textA.state = root.currentScrollMode

        aItem.opacity = 1.0
        aItem.scale = 1.0
        aItem.z = 10
        bItem.opacity = 0.0
        bItem.z = 0
        
        if (type === "image") {
            playerA.stop()
            imageA.source = url
            imageA.visible = true
            videoA.visible = false
            textA.visible = false
            imgTimer.restart()
        } else if (type === "text") {
            playerA.stop()
            textA.text = url
            textA.visible = true
            imageA.visible = false
            videoA.visible = false
            imgTimer.restart()
        } else {
            imageA.visible = false
            videoA.visible = true
            textA.visible = false
            playerA.stop()
            playerA.source = url
            playerA.audioOutput.volume = 1.0
            playerA.play()
            imgTimer.stop()
        }
    }

    function startFade() {
        if (root.isFading) return
        if (!root.nextReady) return
        
        // console.log("Starting fade")
        root.isFading = true
        root.transitionStarted()
        
        if (root.activeIsA) {
            // Transition A -> B
            // Ensure B is prepared
            if (root.nextType === "video") {
                playerB.audioOutput.volume = 1.0
                // playerB.play() // Should be already playing or paused
            }
            
            bItem.z = 10
            aItem.z = 0
            // Reset B transform just in case
            bItem.scale = 1.1
            bItem.opacity = 0.0
            
            crossAtoB.start()
        } else {
            // Transition B -> A
            if (root.nextType === "video") {
                playerA.audioOutput.volume = 1.0
                if (playerA.playbackState !== MediaPlayer.PlayingState) {
                    playerA.play()
                }
            }
            
            aItem.z = 10
            bItem.z = 0
            aItem.scale = 1.1
            aItem.opacity = 0.0
            
            crossBtoA.start()
        }
    }
    
    function finalizeFade() {
        // console.log("Finalize fade")
        var oldPlayer = root.activeIsA ? playerA : playerB
        var oldType = root.currentType
        
        if (oldType === "video") {
            oldPlayer.stop()
        }
        
        // Swap active
        root.activeIsA = !root.activeIsA
        root.currentUrl = root.nextUrl
        root.currentType = root.nextType
        root.currentScrollMode = root.nextScrollMode
        root.mediaInfo("Playing: " + root.currentUrl)
        root.nextReady = false
        
        // Reset scale of new active item
        if (root.activeIsA) {
            aItem.scale = 1.0
        } else {
            bItem.scale = 1.0
        }
        
        // Update duration
        root.imageDurationMs = root.nextDurationMs
        
        // Start timer if image
        if (root.currentType === "image" || root.currentType === "text") {
            imgTimer.restart()
        } else {
            imgTimer.stop()
        }
        
        // Start scroll animation if needed
        if (root.currentType === "text" && root.currentScrollMode === "scroll") {
             if (root.activeIsA) scrollAnimA.restart()
             else scrollAnimB.restart()
        }
        
        root.isFading = false
        root.transitionFinished()
        root.mediaFinished(root.currentUrl, root.currentType) // Notify Python to schedule next
    }
    
    Timer {
        id: imgTimer
        interval: root.imageDurationMs
        repeat: false
        onTriggered: {
            if ((root.currentType === "image" || root.currentType === "text") && !root.isFading && root.nextReady) {
                startFade()
            }
        }
    }
    
    // Content Items
    Item {
        id: aItem
        anchors.fill: parent
        opacity: 1.0
        z: 10
        
        Rectangle {
            id: bgA
            anchors.fill: parent
            color: "black"
            z: 0
        }
        
        Image {
            id: imageA
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            visible: false
            smooth: true
            mipmap: true
            z: 1
        }
        Text {
            id: textA
            anchors.fill: parent
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 80
            color: "white"
            wrapMode: Text.Wrap
            visible: false
            style: Text.Outline
            styleColor: "black"
            z: 2
            
            states: [
                State {
                    name: "static"
                    AnchorChanges { target: textA; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.verticalCenter: undefined }
                    PropertyChanges { target: textA; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                },
                State {
                    name: "scroll"
                    AnchorChanges { target: textA; anchors.left: undefined; anchors.right: undefined; anchors.top: undefined; anchors.bottom: undefined; anchors.verticalCenter: parent.verticalCenter }
                    PropertyChanges { target: textA; wrapMode: Text.NoWrap; horizontalAlignment: Text.AlignLeft; verticalAlignment: Text.AlignVCenter; x: parent.width }
                }
            ]
        }
        
        NumberAnimation {
            id: scrollAnimA
            target: textA
            property: "x"
            from: parent.width
            to: -textA.contentWidth
            duration: root.imageDurationMs
            running: false
        }
        
        MediaPlayer {
            id: playerA
            audioOutput: AudioOutput {}
            videoOutput: videoA
            onMediaStatusChanged: {
                 if (root.activeIsA && root.currentType === "video" && !root.isFading) {
                     if (status === MediaPlayer.EndOfMedia) {
                         if (root.nextReady) {
                             startFade()
                         } else {
                             root.mediaInfo("Player A finished but next not ready. Waiting...")
                         }
                     }
                 }
            }
            onErrorOccurred: {
                root.mediaInfo("Player A Error: " + errorString)
                // Auto-skip on error if current
                if (root.activeIsA && root.currentType === "video" && !root.isFading) {
                    root.mediaInfo("Player A error during playback. Forcing next.")
                    // If next is ready, fade. If not, emit finished to provoke next.
                    if (root.nextReady) {
                        startFade()
                    } else {
                        // Force Python to send next immediately
                        root.mediaFinished(root.currentUrl, root.currentType)
                    }
                }
            }
        }
        VideoOutput {
            id: videoA
            anchors.fill: parent
            visible: false
            fillMode: VideoOutput.PreserveAspectFit
            z: 5
        }
    }
    
    Item {
        id: bItem
        anchors.fill: parent
        opacity: 0.0
        z: 0
        
        Rectangle {
            id: bgB
            anchors.fill: parent
            color: "black"
            z: 0
        }
        
        Image {
            id: imageB
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            visible: false
            smooth: true
            mipmap: true
            z: 1
        }
        Text {
            id: textB
            anchors.fill: parent
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 80
            color: "white"
            wrapMode: Text.Wrap
            visible: false
            style: Text.Outline
            styleColor: "black"
            z: 2
            
            states: [
                State {
                    name: "static"
                    AnchorChanges { target: textB; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.verticalCenter: undefined }
                    PropertyChanges { target: textB; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                },
                State {
                    name: "scroll"
                    AnchorChanges { target: textB; anchors.left: undefined; anchors.right: undefined; anchors.top: undefined; anchors.bottom: undefined; anchors.verticalCenter: parent.verticalCenter }
                    PropertyChanges { target: textB; wrapMode: Text.NoWrap; horizontalAlignment: Text.AlignLeft; verticalAlignment: Text.AlignVCenter; x: parent.width }
                }
            ]
        }
        
        NumberAnimation {
            id: scrollAnimB
            target: textB
            property: "x"
            from: parent.width
            to: -textB.contentWidth
            duration: root.imageDurationMs
            running: false
        }
        
        MediaPlayer {
            id: playerB
            audioOutput: AudioOutput {}
            videoOutput: videoB
            onMediaStatusChanged: {
                 root.mediaInfo("Player B Status: " + status)
                 if (!root.activeIsA && root.currentType === "video" && !root.isFading) {
                     if (status === MediaPlayer.EndOfMedia) {
                         if (root.nextReady) {
                             startFade()
                         } else {
                             root.mediaInfo("Player B finished but next not ready. Waiting...")
                         }
                     }
                 }
            }
            onPlaybackStateChanged: {
                root.mediaInfo("Player B State: " + playbackState)
            }
            onErrorOccurred: {
                root.mediaInfo("Player B Error: " + errorString + " (" + error + ")")
                // Auto-skip on error if current
                if (!root.activeIsA && root.currentType === "video" && !root.isFading) {
                    root.mediaInfo("Player B error during playback. Forcing next.")
                    if (root.nextReady) {
                        startFade()
                    } else {
                        root.mediaFinished(root.currentUrl, root.currentType)
                    }
                }
            }
        }
        VideoOutput {
            id: videoB
            anchors.fill: parent
            visible: false
            fillMode: VideoOutput.PreserveAspectFit
            z: 5
        }
    }
    
    // Animations
    ParallelAnimation {
        id: crossAtoB
        NumberAnimation { target: aItem; property: "opacity"; from: 1.0; to: 0.0; duration: root.fadeMs; easing.type: Easing.OutQuad }
        NumberAnimation { target: aItem; property: "scale"; from: 1.0; to: 0.8; duration: root.fadeMs; easing.type: Easing.OutQuad }
        NumberAnimation { target: bItem; property: "opacity"; from: 0.0; to: 1.0; duration: root.fadeMs; easing.type: Easing.OutQuad }
        NumberAnimation { target: bItem; property: "scale"; from: 1.1; to: 1.0; duration: root.fadeMs; easing.type: Easing.OutQuad }
        onFinished: finalizeFade()
    }
    ParallelAnimation {
        id: crossBtoA
        NumberAnimation { target: bItem; property: "opacity"; from: 1.0; to: 0.0; duration: root.fadeMs; easing.type: Easing.OutQuad }
        NumberAnimation { target: bItem; property: "scale"; from: 1.0; to: 0.8; duration: root.fadeMs; easing.type: Easing.OutQuad }
        NumberAnimation { target: aItem; property: "opacity"; from: 0.0; to: 1.0; duration: root.fadeMs; easing.type: Easing.OutQuad }
        NumberAnimation { target: aItem; property: "scale"; from: 1.1; to: 1.0; duration: root.fadeMs; easing.type: Easing.OutQuad }
        onFinished: finalizeFade()
    }
}
