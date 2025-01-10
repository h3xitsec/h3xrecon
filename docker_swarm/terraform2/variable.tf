variable "tenancy_ocid" {
 default="ocid1.tenancy.oc1..aaaaaaaaj2ypzguxundpxxniiitrs6r3zts4dccs55wqiyo5scrxmjzb63na"
 description="OCI Personal Tenancy -- No worries" 
}

variable "user_ocid"  {
 default = "ocid1.user.oc1..aaaaaaaaeixyyeyyvfqh6iyme3ie4jden3a7e4wqkq36vnmvq3tofosjpwrq"
}

variable "private_key_path" {
 default = "/home/h3x/.oci/oci_api_key.pem"
}

variable "ssh_public_key_file" {
  default = "/home/h3x/.ssh/id_ed25519.pub"
}

variable "fingerprint" {
 default = "ec:05:d7:af:4a:04:fa:44:20:d5:88:3b:d3:96:c8:44"
}

variable "compute_cpus" {
 type = string
 default = "1" 
}

variable "compute_memory_in_gbs" {
 type = string
 default = "6"
}


variable "cpu_core_count" {
  type    = number
  default = 1
}

variable "data_storage_size_in_gb" {
  type    = number
  default = 45
}

variable "db_name" {
 default = "Choice_your_database_name"
}

variable "db_version" {
     default = "21c"
}

variable "license_model" {
 default = "LICENSE_INCLUDED" 
}

variable "admin_password" {
        default = "qwerty123!*"
}

variable "is_free_tier" {
        default = "true"
}

variable "db_workload" {
 default = "DW"
}

variable "ad_number" {
    default = "1"
}

variable "region" {
 default = "ca-montreal-1"
}

variable "root_compartment_id" {
 default = "ocid1.tenancy.oc1..aaaaaaaaj2ypzguxundpxxniiitrs6r3zts4dccs55wqiyo5scrxmjzb63na"
}

variable "compartment_display_name" {
 default = "h3xrecon"
}

variable "public_subnet_name" {
        default = "h3xrecon_subnet"
}

variable  "label_prefix" {
 default = "none"
}

/*
variable "tags" {
  description = "simple key-value pairs to tag the resources created using freeform tags."
  type   = map(any)
  default = {
    environment = "testing"
    project = "test-first-phase"
  }
}
*/

variable "instance_shape" {
    default = "VM.Standard.A1.Flex"
}


variable "vcn_name" {
  description = "user-friendly name of to use for the vcn to be appended to the label_prefix"
  type        = string
  default = "testing"
}

variable "vcn_dns_label" {
  description = "A DNS label for the VCN, used in conjunction with the VNIC's hostname and subnet's DNS label to form a fully qualified domain name (FQDN) for each VNIC within this subnet"
  type        = string
  default = "ocitesting"
}

variable "vcn_cidr" {
  description = "cidr block of VCN"
  default     = "10.0.0.0/16"
  type        = string
}

variable "sub_cidr" {
  default     = "10.0.0.0/22"
  }

variable "internet_gateway_enabled" {
  type = bool
  default = "true"
}

variable "test-ports" {
  default = [22,80,443]
}

variable "worker_ol_image_name" {
  default = "Oracle-Linux-8-2022.10.04-0"
}
