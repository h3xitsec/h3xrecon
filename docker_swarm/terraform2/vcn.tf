resource "oci_core_vcn" "testvcn" {
  cidr_block     = var.vcn_cidr
  compartment_id = var.root_compartment_id
  display_name   = var.label_prefix == "none" ? var.vcn_name : "${var.label_prefix}-${var.vcn_name}"
  dns_label      = var.vcn_dns_label
}
