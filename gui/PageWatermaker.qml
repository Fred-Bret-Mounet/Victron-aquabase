import QtQuick 2
import com.victron.velib 1.0
import "utils.js" as Utils

MbPage {
	id: root
	title: qsTr("Watermaker")
	property string bindPrefix: "com.victronenergy.watermaker.aquabase"

	VBusItem { id: connectedItem; bind: Utils.path(root.bindPrefix, "/Connected") }
	property bool deviceConnected: connectedItem.valid && connectedItem.value === 1

	model: VisibleItemModel {
		MbItemValue {
			description: qsTr("Connection")
			item.bind: Utils.path(root.bindPrefix, "/Connected")
			item.text: item.valid && item.value === 1 ? qsTr("Connected") : qsTr("Disconnected")
		}
		MbItemValue {
			description: qsTr("State")
			item.bind: Utils.path(root.bindPrefix, "/State")
			show: root.deviceConnected
			item.text: {
				if (!item.valid) return ""
				switch (item.value) {
					case 0: return qsTr("Stopped")
					case 1: return qsTr("Running")
					case 2: return qsTr("Washing")
					default: return "?"
				}
			}
		}
		MbItemValue {
			description: qsTr("Flow")
			item.bind: Utils.path(root.bindPrefix, "/CurrentFlow")
			show: root.deviceConnected
			item.unit: " L/h"
		}
		MbItemValue {
			description: qsTr("Salinity")
			item.bind: Utils.path(root.bindPrefix, "/Salinity")
			show: root.deviceConnected
			item.unit: " ppm"
		}
		MbItemValue {
			description: qsTr("Salinity threshold")
			item.bind: Utils.path(root.bindPrefix, "/SalinityThreshold")
			show: root.deviceConnected
			item.unit: " ppm"
		}
		MbItemValue {
			description: qsTr("Quality")
			item.bind: Utils.path(root.bindPrefix, "/Quality")
			show: root.deviceConnected
			item.text: item.valid ? (item.value === 1 ? qsTr("OK") : qsTr("NOK")) : ""
		}
		MbItemValue {
			description: qsTr("Operating hours")
			item.bind: Utils.path(root.bindPrefix, "/HoursOperation")
			show: root.deviceConnected
			item.unit: " h"
		}
		MbItemValue {
			description: qsTr("Model")
			item.bind: Utils.path(root.bindPrefix, "/Model")
			show: root.deviceConnected
		}
		MbItemValue {
			description: qsTr("Serial number")
			item.bind: Utils.path(root.bindPrefix, "/Serial")
			show: root.deviceConnected
		}
		MbItemValue {
			description: qsTr("Commissioned")
			item.bind: Utils.path(root.bindPrefix, "/CommissionDate")
			show: root.deviceConnected
		}
		MbItemValue {
			description: qsTr("Last event")
			item.bind: Utils.path(root.bindPrefix, "/LastEventDescription")
			show: root.deviceConnected
		}
	}
}
