from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
import os
import logging

# Airflow 버전 호환성을 위한 PythonOperator import
try:
    # Airflow 3.0+ 버전용 (표준 프로바이더)
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:
    try:
        # Airflow 2.8+ 버전용 (기존 경로)
        from airflow.operators.python import PythonOperator
    except ImportError:
        # Airflow 2.7 이하 버전용
        from airflow.operators.python_operator import PythonOperator

# 기본 DAG 설정
default_args = {
    'owner': 'scenario-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 6, 13),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'scenario_generation_pipeline_docker',
    default_args=default_args,
    description='시나리오 생성 및 전송 파이프라인 (DockerOperator)',
    schedule_interval='0 9 * * *',
    catchup=False,
    tags=['scenario', 'generation', 'json'],
)

IMAGE_NAME = "hwpar0826/scenario_app:latest"  # ← 실제 이미지명으로 교체

# 호스트 <-> 컨테이너 공유 볼륨
VOLUME_MAP = [
    '/opt/airflow/news_json_files:/app/news_json_files',
    '/opt/airflow/result_json_files:/app/result_json_files'
]


def clean_json_files():
    """
    /opt/airflow/news_json_files와 /opt/airflow/result_json_files
    내부의 모든 파일 및 빈 디렉토리를 삭제합니다.
    """
    dirs_to_clean = [
        '/opt/airflow/news_json_files',
        '/opt/airflow/result_json_files'
    ]

    for dir_path in dirs_to_clean:
        if os.path.exists(dir_path):
            # 디렉토리 내 파일 및 빈 하위 디렉토리 삭제
            for root, dirs, files in os.walk(dir_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        logging.info(f"삭제됨: {file_path}")
                    except Exception as e:
                        logging.error(f"파일 삭제 실패: {file_path}, 에러: {e}")
                # 빈 하위 디렉토리 삭제
                for dir in dirs:
                    dir_path_to_remove = os.path.join(root, dir)
                    if os.path.exists(dir_path_to_remove) and not os.listdir(dir_path_to_remove):
                        try:
                            os.rmdir(dir_path_to_remove)
                            logging.info(f"빈 디렉토리 삭제됨: {dir_path_to_remove}")
                        except Exception as e:
                            logging.error(f"디렉토리 삭제 실패: {dir_path_to_remove}, 에러: {e}")
        else:
            logging.info(f"디렉토리가 존재하지 않음: {dir_path}")

    logging.info("news/result JSON 파일 정리 완료")
    print("news/result JSON 파일 정리 완료")

# 1. 결과파일 삭제용 clean task (컨테이너에 clean_files.py 필요)
clean_task = PythonOperator(
    task_id='clean_json_files',
    python_callable=clean_json_files,
    dag=dag,
)

# 2. 각 테마별 시나리오 생성 Task
themes = ['pig', 'food', 'magic', 'moon']
generation_tasks = []
for theme in themes:
    task = DockerOperator(
        task_id=f'generate_{theme}_scenarios',
        image=IMAGE_NAME,
        command=f"--theme {theme} --n 1",
        docker_kwargs={"volumes": VOLUME_MAP},
        auto_remove=True,
        dag=dag,
        do_xcom_push=False,
    )
    generation_tasks.append(task)

# 3. 시나리오 전송 Task (send_data.py 실행)
send_task = DockerOperator(
    task_id='send_scenarios',
    image=IMAGE_NAME,
    command="python send_data.py",
    volumes=VOLUME_MAP,
    auto_remove=True,
    dag=dag,
    do_xcom_push=False,
)

# 4. Task 의존성
clean_task >> generation_tasks[0] >> generation_tasks[1] >> generation_tasks[2] >> generation_tasks[3] >> send_task
