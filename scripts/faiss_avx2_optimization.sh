#!/bin/bash
# 安装支持 AVX2 的 FAISS（可选优化）

echo "当前 FAISS 版本："
python -c "import faiss; print(faiss.__version__)" 2>&1 || echo "FAISS 未安装"

echo ""
echo "可选优化：重新安装 FAISS 以支持 AVX2"
echo "命令：pip install --upgrade --force-reinstall faiss-cpu"
echo ""
echo "注意：这是性能优化，不影响基本功能"
echo "警告信息：Could not load library with AVX2 support"
echo "原因：缺少 faiss.swigfaiss_avx2 模块"
echo "影响：向量计算速度稍慢，但功能正常"