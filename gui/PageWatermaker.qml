import QtQuick 2
import com.victron.velib 1.0
import "utils.js" as Utils

MbPage {
	id: root
	title: qsTr("Watermaker")
	property string bindPrefix: "com.victronenergy.watermaker.aquabase"

	model: VisibleItemModel {
		MbItemValue {
			description: qsTr("Connection")
			item.bind: Utils.path(root.bindPrefix, "/Connected")
			item.text: item.valid && item.value === 1 ? qsTr("Connected") : qsTr("Disconnected")
		}
		MbItemValue {
			description: qsTr("State")
			item.bind: Utils.path(root.bindPrefix, "/State")
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
			item.unit: " L/h"
		}
		MbItemValue {
			description: qsTr("Salinity")
			item.bind: Utils.path(root.bindPrefix, "/Salinity")
			item.unit: " ppm"
		}
		MbItemValue {
			description: qsTr("Salinity threshold")
			item.bind: Utils.path(root.bindPrefix, "/SalinityThreshold")
			item.unit: " ppm"
		}
		MbItemValue {
			description: qsTr("Quality")
			item.bind: Utils.path(root.bindPrefix, "/Quality")
			item.text: item.valid ? (item.value === 1 ? qsTr("OK") : qsTr("NOK")) : ""
		}
		MbItemValue {
			description: qsTr("Operating hours")
			item.bind: Utils.path(root.bindPrefix, "/HoursOperation")
			item.unit: " h"
		}
		MbItemValue {
			description: qsTr("Model")
			item.bind: Utils.path(root.bindPrefix, "/Model")
		}
		MbItemValue {
			description: qsTr("Serial number")
			item.bind: Utils.path(root.bindPrefix, "/Serial")
		}
		MbItemValue {
			description: qsTr("Commissioned")
			item.bind: Utils.path(root.bindPrefix, "/CommissionDate")
		}
		MbItemValue {
			description: qsTr("Last event")
			item.bind: Utils.path(root.bindPrefix, "/LastEventDescription")
		}
	}
}
