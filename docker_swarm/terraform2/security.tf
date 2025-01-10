resource "oci_core_security_list" "sl" {
    compartment_id = var.root_compartment_id
    vcn_id = oci_core_vcn.testvcn.id
    display_name = "sl-test"
    
    egress_security_rules {
        destination = "0.0.0.0/0"
 destination_type = "CIDR_BLOCK"
        protocol = "all"
 stateless = false
    }
    ingress_security_rules {
     stateless   = false
     source      = "0.0.0.0/0"
     source_type = "CIDR_BLOCK"
     protocol    = "6"
     tcp_options {
      min = 22 
      max = 22 
     }
   }
   ingress_security_rules {
     stateless   = false
     source      = "0.0.0.0/0"
     source_type = "CIDR_BLOCK"
     protocol    = "1"
     icmp_options {
      type = 3
      code = 4
     }
   }
}


output "public_security_list_id" {
  value = oci_core_security_list.sl.id
}

output "public_subnet_id" {
  value = oci_core_subnet.subnet1.id
} 
