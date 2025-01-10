resource "oci_core_internet_gateway" "ig" {
    compartment_id = var.root_compartment_id
    vcn_id = oci_core_vcn.testvcn.id
    enabled = var.internet_gateway_enabled
    display_name = "ig-test"
}
