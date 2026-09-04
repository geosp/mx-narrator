import torch

available = torch.cuda.is_available()
print(f"cuda_available: {available}")
if available:
    print(f"device_name: {torch.cuda.get_device_name(0)}")
