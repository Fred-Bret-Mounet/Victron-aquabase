import QtQuick
import Victron.VenusOS

DeviceListPluginPage {
	id: root

	title: "Watermaker"

	GradientListView {
		model: VisibleItemModel {
			ListRadioButtonGroup {
				text: "Command"
				dataItem.uid: root.device.serviceUid + "/Mode"
				preferredVisible: dataItem.valid && connectedItem.value === 1
				// Only allow transitions that make sense from the current
				// reported /State: stopped → Start or Wash; running or
				// washing → Stop. The current state stays selectable so
				// the picker visibly reflects what the device is doing.
				optionModel: [
					{ display: "Stop",  value: 0, readOnly: stateItem.value === 0 },
					{ display: "Start", value: 1, readOnly: stateItem.value !== 0 },
					{ display: "Wash",  value: 2, readOnly: stateItem.value !== 0 },
				]
				VeQuickItem { id: connectedItem; uid: root.device.serviceUid + "/Connected" }
				VeQuickItem { id: stateItem;     uid: root.device.serviceUid + "/State" }
			}
			ListSwitch {
				text: "Auto-stop"
				dataItem.uid: root.device.serviceUid + "/AutoStop/Enabled"
				preferredVisible: dataItem.valid && connectedItem.value === 1
			}
			ListRadioButtonGroup {
				text: "Auto-stop mode"
				dataItem.uid: root.device.serviceUid + "/AutoStop/Mode"
				preferredVisible: dataItem.valid && connectedItem.value === 1
					&& autoStopEnabledItem.value === 1
				optionModel: [
					{ display: "Time (min)",  value: 0 },
					{ display: "Volume (L)", value: 1 },
				]
				VeQuickItem { id: autoStopEnabledItem; uid: root.device.serviceUid + "/AutoStop/Enabled" }
			}
			ListSpinBox {
				text: "Auto-stop target"
				dataItem.uid: root.device.serviceUid + "/AutoStop/Target"
				preferredVisible: dataItem.valid && connectedItem.value === 1
					&& autoStopEnabledItem.value === 1
				from: 1
				to: 9999
				stepSize: 1
				suffix: autoStopModeItem.value === 1 ? " L" : " min"
				VeQuickItem { id: autoStopModeItem; uid: root.device.serviceUid + "/AutoStop/Mode" }
			}
			ListText {
				text: "Connection"
				dataItem.uid: root.device.serviceUid + "/Connected"
				secondaryText: !dataItem.valid ? ""
					: (dataItem.value === 1 ? "Connected" : "Disconnected")
			}
			ListText {
				text: "State"
				dataItem.uid: root.device.serviceUid + "/State"
				secondaryText: {
					if (!dataItem.valid) return ""
					switch (dataItem.value) {
						case 0: return "Stopped"
						case 1: return "Running"
						case 2: return "Washing"
						default: return ""
					}
				}
			}
			ListText {
				text: "Flow"
				dataItem.uid: root.device.serviceUid + "/CurrentFlow"
				preferredVisible: dataItem.valid
				secondaryText: dataItem.valid ? dataItem.value + " L/h" : ""
			}
			ListText {
				text: "Salinity"
				dataItem.uid: root.device.serviceUid + "/Salinity"
				preferredVisible: dataItem.valid
				secondaryText: dataItem.valid ? dataItem.value + " ppm" : ""
			}
			ListText {
				text: "Salinity threshold"
				dataItem.uid: root.device.serviceUid + "/SalinityThreshold"
				preferredVisible: dataItem.valid
				secondaryText: dataItem.valid ? dataItem.value + " ppm" : ""
			}
			ListText {
				text: "Quality"
				dataItem.uid: root.device.serviceUid + "/Quality"
				preferredVisible: dataItem.valid
				secondaryText: dataItem.valid ? (dataItem.value === 1 ? "OK" : "NOK") : ""
			}
			ListText {
				text: "Operating hours"
				dataItem.uid: root.device.serviceUid + "/HoursOperation"
				preferredVisible: dataItem.valid
				secondaryText: dataItem.valid
					? Number(dataItem.value).toFixed(1) + " h" : ""
			}
			ListText {
				text: "Model"
				dataItem.uid: root.device.serviceUid + "/Model"
				preferredVisible: dataItem.valid && dataItem.value !== ""
				secondaryText: dataItem.value || ""
			}
			ListText {
				text: "Serial number"
				dataItem.uid: root.device.serviceUid + "/Serial"
				preferredVisible: dataItem.valid && dataItem.value !== ""
				secondaryText: dataItem.value || ""
			}
			ListText {
				text: "Commissioned"
				dataItem.uid: root.device.serviceUid + "/CommissionDate"
				preferredVisible: dataItem.valid && dataItem.value !== ""
				secondaryText: dataItem.value || ""
			}
			ListText {
				text: "Last event"
				dataItem.uid: root.device.serviceUid + "/LastEventDescription"
				preferredVisible: dataItem.valid && dataItem.value !== ""
				secondaryText: dataItem.value || ""
			}

			ListSwitch {
				text: "Alert when starting"
				dataItem.uid: Global.systemSettings.serviceUid + "/Settings/Watermaker/Aquabase/AlertOnStart"
			}
			ListSwitch {
				text: "Alert when stopping"
				dataItem.uid: Global.systemSettings.serviceUid + "/Settings/Watermaker/Aquabase/AlertOnStop"
			}
			ListSwitch {
				text: "Alert on flush / wash"
				dataItem.uid: Global.systemSettings.serviceUid + "/Settings/Watermaker/Aquabase/AlertOnWash"
			}
		}
	}
}
