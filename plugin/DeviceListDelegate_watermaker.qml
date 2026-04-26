/*
** Aquabase-watermaker package — gui-v2 device-list row for watermaker services.
*/

import QtQuick
import Victron.VenusOS

DeviceListDelegate {
	id: root

	quantityModel: QuantityObjectModel {
		filterType: QuantityObjectModel.HasValue
		QuantityObject { object: salinity; unit: VenusOS.Units_PartsPerMillion }
		QuantityObject { object: flow; unit: VenusOS.Units_None }
	}

	onClicked: {
		Global.pageManager.pushPage(
			"qrc:/aquabase-watermaker/AquabaseWatermaker_PageWatermaker.qml",
			{ device: root.device })
	}

	VeQuickItem { id: salinity; uid: root.device.serviceUid + "/Salinity" }
	VeQuickItem { id: flow;     uid: root.device.serviceUid + "/CurrentFlow" }
}
