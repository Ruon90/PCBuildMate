from django.db import models

class PSU(models.Model):
    brand = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=200, blank=True, null=True)
    psu_type = models.CharField(max_length=100, blank=True, null=True)
    efficiency = models.CharField(max_length=100, blank=True, null=True)
    wattage = models.IntegerField(blank=True, null=True)
    modular = models.CharField(max_length=100, blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)


class CPU(models.Model):
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    socket = models.CharField(max_length=50, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    core_count = models.IntegerField(blank=True, null=True)
    core_clock = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    boost_clock = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    microarchitecture = models.CharField(max_length=100, blank=True, null=True)
    tdp = models.IntegerField(blank=True, null=True)
    graphics = models.CharField(max_length=100, blank=True, null=True)
    thread_count = models.IntegerField(blank=True, null=True)
    userbenchmark_score = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    blender_score = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    power_consumption_overclocked = models.IntegerField(blank=True, null=True)


class GPU(models.Model):
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    gpu_name = models.CharField(max_length=100, blank=True, null=True)
    userbenchmark_score = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    userbenchmark_url = models.URLField(blank=True, null=True)
    blender_score = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True, null=True)
    generation = models.CharField(max_length=50, blank=True, null=True)
    base_clock = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    boost_clock = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    architecture = models.CharField(max_length=50, blank=True, null=True)
    process_size = models.IntegerField(blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    bus_interface = models.CharField(max_length=50, blank=True, null=True)
    memory_clock = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    memory_size_gb = models.IntegerField(blank=True, null=True)
    memory_type = models.CharField(max_length=50, blank=True, null=True)
    shading_units = models.IntegerField(blank=True, null=True)
    tmus = models.IntegerField(blank=True, null=True)
    rops = models.IntegerField(blank=True, null=True)
    sms = models.IntegerField(blank=True, null=True)
    tensor_cores = models.IntegerField(blank=True, null=True)
    rt_cores = models.IntegerField(blank=True, null=True)
    l1_cache_kb = models.IntegerField(blank=True, null=True)
    l2_cache_mb = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    tdp = models.IntegerField(blank=True, null=True)
    board_length = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    board_width = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    slot_width = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    suggested_psu = models.CharField(max_length=50, blank=True, null=True)
    power_connectors = models.CharField(max_length=100, blank=True, null=True)
    display_connectors = models.CharField(max_length=200, blank=True, null=True)


class Motherboard(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    socket = models.CharField(max_length=50, blank=True, null=True)
    form_factor = models.CharField(max_length=50, blank=True, null=True)
    max_memory = models.IntegerField(blank=True, null=True)
    memory_slots = models.IntegerField(blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    ddr_version = models.CharField(max_length=10, blank=True, null=True)
    ddr_max_speed = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    nvme_support = models.CharField(max_length=50, blank=True, null=True)
    bios_update_required = models.BooleanField(blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True, null=True)


class RAM(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    modules = models.IntegerField(blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    first_word_latency = models.IntegerField(blank=True, null=True)
    cas_latency = models.IntegerField(blank=True, null=True)
    ddr_generation = models.CharField(max_length=10, blank=True, null=True)
    frequency_mhz = models.IntegerField(blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True, null=True)
    capacity_gb = models.IntegerField(blank=True, null=True)
    benchmark = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)


class Storage(models.Model):
    brand = models.CharField(max_length=100, blank=True, null=True)
    model = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    capacity = models.IntegerField(blank=True, null=True)
    storage_type = models.CharField(max_length=100, blank=True, null=True)
    cache = models.IntegerField(blank=True, null=True)
    form_factor = models.CharField(max_length=100, blank=True, null=True)
    interface = models.CharField(max_length=100, blank=True, null=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)


class CPUCooler(models.Model):
    name = models.CharField(max_length=200, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    rpm = models.CharField(max_length=50, blank=True, null=True)          
    noise_level = models.CharField(max_length=50, blank=True, null=True)  
    color = models.CharField(max_length=100, blank=True, null=True)
    size = models.DecimalField(max_digits=6, decimal_places=1, blank=True, null=True)  
    liquid = models.BooleanField(blank=True, null=True)
    power_throughput = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)



class Case(models.Model):
    name = models.CharField(max_length=200, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    case_type = models.CharField(max_length=100, blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    psu = models.CharField(max_length=100, blank=True, null=True)
    side_panel = models.CharField(max_length=200, blank=True, null=True)
    external_volume = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    internal_35_bays = models.IntegerField(blank=True, null=True)
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)

class ThermalPaste(models.Model):
    name = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    amount = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)  # grams or ml
    slug = models.SlugField(max_length=200, unique=True, blank=True, null=True)
