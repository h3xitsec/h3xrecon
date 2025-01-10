resource "oci_core_route_table" "rt" {
    compartment_id = var.root_compartment_id
    vcn_id = oci_core_vcn.testvcn.id
    display_name = "rt-test"
    route_rules {
        destination = "0.0.0.0/0"
        destination_type = "CIDR_BLOCK"
        network_entity_id = oci_core_internet_gateway.ig.id
    }
}
