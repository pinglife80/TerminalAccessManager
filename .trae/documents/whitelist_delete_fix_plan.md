# 代码提交计划

## 修改文件
- `backend/app/api/v1/endpoints/whitelist.py`
- `backend/app/services/terminal_service.py`
- `frontend/src/pages/Whitelist.tsx`

## 提交步骤
1. `./manage.sh test`
2. `git diff`
3. `git add . && git commit -m "fix(whitelist): fix deletion 404 errors"`
4. `git push origin develop`
5. 创建PR到main
6. 代码审查
7. 部署