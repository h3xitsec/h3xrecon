
resource "oci_core_subnet" "subnet1" {
    cidr_block = var.sub_cidr
    compartment_id = var.root_compartment_id
    vcn_id = oci_core_vcn.testvcn.id
    display_name = "Anyname-subnet"
    route_table_id = oci_core_route_table.rt.id
    security_list_ids = [oci_core_security_list.sl.id]
}
