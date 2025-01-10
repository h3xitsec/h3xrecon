data "oci_core_images" "ubuntu-22-04" {
  compartment_id = var.root_compartment_id
  operating_system = "Canonical Ubuntu"
  filter {
    name = "display_name"
    values = ["^Canonical-Ubuntu-22.04-([\\.0-9-]+)$"]
    regex = true
  }
}

output "show_image" {
  value = data.oci_core_images.ubuntu-22-04.images[0].id
}

data "oci_identity_compartments" "GetCompartments" {
 compartment_id = "${var.tenancy_ocid}"
 filter {
  name = "name"
 values = ["{var.compartment_display_name}"]
 }
}

output "showCompartment" {
  value = data.oci_identity_compartments.GetCompartments
}


data "oci_identity_availability_domains" "GetAds" {
 compartment_id = var.root_compartment_id 
}

output "show_ads" {
  value = data.oci_identity_availability_domains.GetAds.availability_domains[0].name 
}

resource "oci_core_instance" "h3xrecon_instance" {
    count = 1
    availability_domain = data.oci_identity_availability_domains.GetAds.availability_domains[0].name
    compartment_id = var.root_compartment_id
    shape = var.instance_shape
    display_name        = "h3xrecon-${count.index + 1}"
    metadata = { 
      ssh_authorized_keys = file("/home/h3x/.ssh/id_ed25519.pub") 
    }
  shape_config {
      ocpus = 1
      memory_in_gbs = 6
  }
    create_vnic_details {
    subnet_id = oci_core_subnet.subnet1.id
    assign_public_ip = true
  }
source_details {
  source_id  = "ocid1.image.oc1.ca-montreal-1.aaaaaaaavjsa47h4stb7n5h43epia7bnkxzyl63epq5kubj2kizy4msxyywa"
  source_type = "image"
  #boot_volume_size_in_gbs = "50"
}
preserve_boot_volume = false
}

output "instance_public_ips" {
  value = {
    for instance in oci_core_instance.h3xrecon_instance :
    instance.display_name => instance.public_ip
  }
}

# output "instance_compute_id" {
#   value = oci_core_instance.logging.id
# }

# output "instance_compute_state" {
#   value = oci_core_instance.logging.state
# }

# output "instance_compute_public_ip" {
#   value = oci_core_instance.logging.public_ip
# }
