terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.21.0"
    }
  }
}

provider "oci" {
  region           = var.region
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
}

variable "tenancy_ocid" {}
variable "user_ocid" {}
variable "fingerprint" {}
variable "private_key_path" {}
variable "region" {}
variable "compartment_ocid" {}
variable "ssh_public_key" {}

# Get the latest Ubuntu image
variable "instance_image_ocid" {
  type = map(string)
  default = {
    # Ubuntu 22.04 ARM - Oracle-provided image
    "ap-sydney-1" = "ocid1.image.oc1.ap-sydney-1.aaaaaaaavzc4ob44q6tezpkwxo7nqf6zyvd6uhzoliliuuzhw3gj4c2l26ma"
    "ap-melbourne-1" = "ocid1.image.oc1.ap-melbourne-1.aaaaaaaavpiusmygtxpvlnqsyuytcddl6qr3snx6qi5nktjak5cwtpbqbdpa"
    "ap-mumbai-1" = "ocid1.image.oc1.ap-mumbai-1.aaaaaaaapkgp6d5o4bznqce6kdi4wjnwxqzir6l62aqt2yaf4mscnhvyxdxq"
    "ap-osaka-1" = "ocid1.image.oc1.ap-osaka-1.aaaaaaaaf3n2w4gk6uj4bmwbfx2r464nrlzxjbewmj2kxsuqp7vxrocqmofq"
    "ap-tokyo-1" = "ocid1.image.oc1.ap-tokyo-1.aaaaaaaappsxkscys6hxskehvk4m5nxlvp7uskh3yaggq54lv3lnvjlpguya"
    "ap-seoul-1" = "ocid1.image.oc1.ap-seoul-1.aaaaaaaavvqfycngzwjuvp7f4gysz7rj6g6zvkfhf2wbqwnamz3jlhcj7nwq"
    "ap-chuncheon-1" = "ocid1.image.oc1.ap-chuncheon-1.aaaaaaaanod2kc3bw5l3myyd5okw4c46kapdpsu2fqgyswf4lka2hrordlla"
    "me-dubai-1" = "ocid1.image.oc1.me-dubai-1.aaaaaaaad5cqz7qjvz7o4wqspxvvqwjnafzxmgefhxawxjz7mdgrrp4nq75q"
    "uk-london-1" = "ocid1.image.oc1.uk-london-1.aaaaaaaaghm4jkrofd3wdh7yhvlc5oqhkrzrxw7fdpcenc3wbf4g5wr5yjka"
    "uk-cardiff-1" = "ocid1.image.oc1.uk-cardiff-1.aaaaaaaah4o43ddxz2nf4qqwe7yq6k6q6hlh2qedwzqt7aapqfxqy5yk7oaq"
    "eu-frankfurt-1" = "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaa4xluwijh66fts4g42iw7gnixntcmns73ei3hwt2j7lihmswkrada"
    "eu-amsterdam-1" = "ocid1.image.oc1.eu-amsterdam-1.aaaaaaaacw2njhmftuhzlz7bvqw6ggwtvcpstqxk4cgh4uqivjmwkqk66i4a"
    "eu-zurich-1" = "ocid1.image.oc1.eu-zurich-1.aaaaaaaagbgbu7akkg7kl6wjfwejhsqxijygepapkgpzt3j7nvcveo5qzcga"
    "eu-paris-1" = "ocid1.image.oc1.eu-paris-1.aaaaaaaavzqjqukp7nmdfkihnmlviedlwc4mgbqwuqwb2qrdwc7tc7pfhfea"
    "eu-marseille-1" = "ocid1.image.oc1.eu-marseille-1.aaaaaaaakrzwkfxhvzjxkrfxw7474mcqtg5eegkzevwrwqrjf6per7nqz2zq"
    "eu-milan-1" = "ocid1.image.oc1.eu-milan-1.aaaaaaaaqpyai4g4lnxcvghxxsf6hjsq2dwqixjqjhh425ssiuovlnkjblya"
    "eu-stockholm-1" = "ocid1.image.oc1.eu-stockholm-1.aaaaaaaajwxhqg4i5zf2dn74473xwyvwg7xf7r3l3kkz53bfwhqwyvyob5mq"
    "me-jeddah-1" = "ocid1.image.oc1.me-jeddah-1.aaaaaaaabzj4d7ryv2nw4ckqjqxlw4rhy4nfwvwpj2ualw45vk5gkwvkp2za"
    "ap-hyderabad-1" = "ocid1.image.oc1.ap-hyderabad-1.aaaaaaaaaq6ggb4u6p4fgsdcj7o2p4akt5t7gmyjnvootiytrqc5py46v7xq"
    "ap-singapore-1" = "ocid1.image.oc1.ap-singapore-1.aaaaaaaaqeawjwwcpqwl4aq7p4g4vgu4vbkzxydttt4lvshr7g2armvlbk6q"
    "us-phoenix-1" = "ocid1.image.oc1.phx.aaaaaaaapw7bwxw45pwvnrvsyoh3hqdlfyhopqxqwpshkdzxgnwb4xw3gby5q"
    "us-ashburn-1" = "ocid1.image.oc1.iad.aaaaaaaavzjw65d6pngbghgrujb76r7zgh2s64z4wwvubvdd4kv3y6gi5kxa"
    "us-sanjose-1" = "ocid1.image.oc1.us-sanjose-1.aaaaaaaaqudryedi3l4danxy5kxbwqkz3nonewp3jwb5l3tdcikhftthmtga"
    "ca-toronto-1" = "ocid1.image.oc1.ca-toronto-1.aaaaaaaanajb7uklrra5eq2ewx35xfi2aulyohweb2ugik7kc6bdfz6swyha"
    "ca-montreal-1" = "ocid1.image.oc1.ca-montreal-1.aaaaaaaaevwvoc7nmz5atwl4gqyszmvlk4qwqvc7rrzfvh6la4megqyuabna"
    "sa-saopaulo-1" = "ocid1.image.oc1.sa-saopaulo-1.aaaaaaaaprzxhwj7fkxlmvf7iqkjitsnzixnwqr3i3qv3x3u3pkdwjkhzr2q"
    "sa-vinhedo-1" = "ocid1.image.oc1.sa-vinhedo-1.aaaaaaaanqvzm5myfdn3xvgvkw7gj4lhc2j4jkwxfnhk5wbhepwxitbqv7oq"
    "sa-santiago-1" = "ocid1.image.oc1.sa-santiago-1.aaaaaaaatqcxqxkuxcvjyagqsqwvjk7k4nbrnsppkz6h4yqwdfwg4l5ik7kq"
    "il-jerusalem-1" = "ocid1.image.oc1.il-jerusalem-1.aaaaaaaafgok5gj36cnrsqo6a3p72wqpg45s3q32oxkt45fq573obsch2q5q"
    "mx-queretaro-1" = "ocid1.image.oc1.mx-queretaro-1.aaaaaaaanpwjnqaejhai7tqfwlrp3h7yvvjwwrpeztpo4hxx7ndxe7qqwyma"
  }
}

# VCN
resource "oci_core_vcn" "h3x_vcn" {
  cidr_block     = "10.0.0.0/16"
  compartment_id = var.compartment_ocid
  display_name   = "h3x-vcn"
  dns_label      = "h3xvcn"
}

# Internet Gateway
resource "oci_core_internet_gateway" "h3x_ig" {
  compartment_id = var.compartment_ocid
  display_name   = "h3x-internet-gateway"
  vcn_id         = oci_core_vcn.h3x_vcn.id
}

# Route Table
resource "oci_core_route_table" "h3x_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.h3x_vcn.id
  display_name   = "h3x-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.h3x_ig.id
  }
}

# Subnet
resource "oci_core_subnet" "h3x_subnet" {
  cidr_block        = "10.0.1.0/24"
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.h3x_vcn.id
  display_name      = "h3x-subnet"
  dns_label         = "h3xsubnet"
  security_list_ids = [oci_core_security_list.h3x_sl.id]
  route_table_id    = oci_core_route_table.h3x_rt.id
}

# Security List
resource "oci_core_security_list" "h3x_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.h3x_vcn.id
  display_name   = "h3x-security-list"

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }

  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"

    tcp_options {
      min = 22
      max = 22
    }
  }
}

# Instances
resource "oci_core_instance" "h3x_instance" {
  count               = 1
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  compartment_id      = var.compartment_ocid
  display_name        = "h3x-instance-${count.index + 1}"
  shape              = "VM.Standard.E2.1.Micro"

  shape_config {
    memory_in_gbs = 1
    ocpus         = 1
  }

  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid[var.region]
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.h3x_subnet.id
    assign_public_ip = true
    nsg_ids          = []
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key)
  }

  preserve_boot_volume = false
}

# Get Availability Domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Output the public IPs of the instances
output "instance_public_ips" {
  value = {
    for instance in oci_core_instance.h3x_instance :
    instance.display_name => instance.public_ip
  }
}
