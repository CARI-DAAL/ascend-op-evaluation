#include <ATen/ATen.h>
#include <torch/library.h>
#include <acl/acl.h>
#include "torch_npu/csrc/core/npu/NPUStream.h"

// ASC emits host launch stubs with blockDim, l2Ctrl and stream preceding kernel args.
extern "C" void native_add(uint32_t, void*, aclrtStream, uint8_t*, uint8_t*, uint8_t*, uint32_t);
extern "C" void native_reduce_sum(uint32_t, void*, aclrtStream, uint8_t*, uint8_t*, uint32_t);
extern "C" void native_matmul(uint32_t, void*, aclrtStream, uint8_t*, uint8_t*, uint8_t*,
                              uint32_t, uint32_t, uint32_t);

static void check(const at::Tensor& x) {
    TORCH_CHECK(x.is_privateuseone() && x.scalar_type() == at::kFloat && x.is_contiguous(),
                "smoke kernels require contiguous float32 NPU tensors");
    TORCH_CHECK(x.numel() > 0 && x.numel() <= 4096, "smoke input size must be 1..4096");
}
static uint8_t* data(const at::Tensor& x) { return reinterpret_cast<uint8_t*>(x.data_ptr()); }
static at::Tensor add(const at::Tensor& x, const at::Tensor& y) {
    check(x); check(y);
    TORCH_CHECK(x.sizes() == y.sizes() && x.device() == y.device(), "add inputs differ");
    auto out = at::empty_like(x);
    auto stream = c10_npu::getCurrentNPUStream().stream(true);
    native_add(1, nullptr, stream, data(x), data(y), data(out), x.numel());
    return out;
}
static at::Tensor reduce_sum(const at::Tensor& x) {
    check(x);
    auto out = at::empty({}, x.options());
    auto stream = c10_npu::getCurrentNPUStream().stream(true);
    native_reduce_sum(1, nullptr, stream, data(x), data(out), x.numel());
    return out;
}
static at::Tensor matmul(const at::Tensor& x, const at::Tensor& y) {
    check(x); check(y);
    TORCH_CHECK(x.dim() == 2 && y.dim() == 2 && x.size(1) == y.size(0)
                && x.device() == y.device(), "invalid matrix inputs");
    auto out = at::empty({x.size(0), y.size(1)}, x.options());
    auto stream = c10_npu::getCurrentNPUStream().stream(true);
    native_matmul(1, nullptr, stream, data(x), data(y), data(out),
                  x.size(0), x.size(1), y.size(1));
    return out;
}
TORCH_LIBRARY(native_eval_smoke, m) {
    m.def("add(Tensor x, Tensor y) -> Tensor");
    m.def("reduce_sum(Tensor x) -> Tensor");
    m.def("matmul(Tensor x, Tensor y) -> Tensor");
}
TORCH_LIBRARY_IMPL(native_eval_smoke, PrivateUse1, m) {
    m.impl("add", &add);
    m.impl("reduce_sum", &reduce_sum);
    m.impl("matmul", &matmul);
}
